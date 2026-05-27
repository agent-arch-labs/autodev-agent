from __future__ import annotations
from typing import Dict, Type, Optional, List, Tuple
import asyncio
import logging

from agents.base import BaseAgent, CoordinatorAgent
from agents.requirement import (
    RequirementAgent,
    ArchitectAgent,
    FunctionAgent,
    CodingAgent,
    TestAgent,
    RuntimeAgent,
)

logger = logging.getLogger("autodev.factory")


class AgentFactory:
    """
    按用户隔离的 Agent 实例管理工厂（优化版）

    优化点:
    - 每用户独立 asyncio.Lock，不同用户可并行初始化
    - get_agent 采用两阶段锁：快速检查 → 无锁创建 → 原子插入
    - get_coordinator 并行创建所有 Agent
    - 支持 prewarm_user 提前预热

    用法:
        factory = AgentFactory()
        agent = factory.get_agent("user-123", RequirementAgent)
        coordinator = factory.get_coordinator("user-123")
        factory.remove_user("user-123")
    """

    _AGENT_CLASSES: Dict[str, Type[BaseAgent]] = {
        "requirement": RequirementAgent,
        "architect": ArchitectAgent,
        "function": FunctionAgent,
        "coding": CodingAgent,
        "test": TestAgent,
        "runtime": RuntimeAgent,
    }

    def __init__(self, prewarm_count: int = 0):
        self._user_agents: Dict[str, Dict[str, BaseAgent]] = {}
        self._user_coordinators: Dict[str, CoordinatorAgent] = {}
        self._user_locks: Dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    async def get_agent(
        self, user_id: str, agent_class: Type[BaseAgent], **kwargs
    ) -> BaseAgent:
        """
        获取或创建指定用户的 Agent 实例（优化版）

        两阶段锁: 先快检查是否需要创建，如需则无锁创建后原子插入。
        """
        agent_name = agent_class.name
        user_lock = await self._get_user_lock(user_id)

        async with user_lock:
            existing = self._get_cached_agent(user_id, agent_name)
            if existing is not None:
                return existing

        instance = agent_class(**kwargs)

        async with user_lock:
            double_check = self._get_cached_agent(user_id, agent_name)
            if double_check is not None:
                return double_check

            if user_id not in self._user_agents:
                self._user_agents[user_id] = {}
            self._user_agents[user_id][agent_name] = instance
            logger.info(f"为用户 {user_id} 创建 Agent: {agent_name}")
            return instance

    async def get_coordinator(self, user_id: str, **kwargs) -> CoordinatorAgent:
        """
        获取或创建指定用户的 CoordinatorAgent（优化版）

        并行创建所有 Worker Agent，大幅减少首次获取延迟。
        """
        user_lock = await self._get_user_lock(user_id)

        async with user_lock:
            if user_id in self._user_coordinators:
                return self._user_coordinators[user_id]

            agents = await self._create_all_agents_parallel(user_id, **kwargs)

            coordinator = CoordinatorAgent(agents=agents, **kwargs)
            self._user_coordinators[user_id] = coordinator
            logger.info(
                f"为用户 {user_id} 创建 CoordinatorAgent，关联 {len(agents)} 个 Worker"
            )
            return coordinator

    async def prewarm_user(self, user_id: str, **kwargs) -> Dict[str, BaseAgent]:
        """
        预热用户: 并行预创建所有 Agent 实例

        适合在用户登录或首次请求前调用，消除冷启动延迟。
        返回所有 Agent 的 name → instance 映射。

        Args:
            user_id: 用户标识
            **kwargs: 传递给 Agent 构造函数的参数

        Returns:
            Dict[str, BaseAgent]: agent_name → instance
        """
        user_lock = await self._get_user_lock(user_id)

        async with user_lock:
            if user_id in self._user_agents and len(self._user_agents[user_id]) == len(
                self._AGENT_CLASSES
            ):
                return dict(self._user_agents[user_id])

            agents = await self._create_all_agents_parallel(user_id, **kwargs)
            agent_map = {agent.name: agent for agent in agents}
            logger.info(f"预热用户 {user_id}: 创建了 {len(agent_map)} 个 Agent")
            return agent_map

    async def batch_get_agents(
        self, user_id: str, agent_names: Optional[List[str]] = None, **kwargs
    ) -> Dict[str, BaseAgent]:
        """
        批量获取 Agent: 并行创建所有缺失的 Agent

        Args:
            user_id: 用户标识
            agent_names: 需要的 Agent 名称列表，None 表示全部
            **kwargs: 传递给 Agent 构造函数的参数

        Returns:
            Dict[str, BaseAgent]: agent_name → instance
        """
        if agent_names is None:
            agent_names = list(self._AGENT_CLASSES.keys())

        user_lock = await self._get_user_lock(user_id)

        async with user_lock:
            need_create: List[Tuple[str, Type[BaseAgent]]] = []
            cached: Dict[str, BaseAgent] = {}

            for name in agent_names:
                existing = self._get_cached_agent(user_id, name)
                if existing is not None:
                    cached[name] = existing
                elif name in self._AGENT_CLASSES:
                    need_create.append((name, self._AGENT_CLASSES[name]))

        for name, cls in need_create:
            instance = cls(**kwargs)

            async with user_lock:
                double_check = self._get_cached_agent(user_id, name)
                if double_check is not None:
                    cached[name] = double_check
                else:
                    if user_id not in self._user_agents:
                        self._user_agents[user_id] = {}
                    self._user_agents[user_id][name] = instance
                    cached[name] = instance

        async with user_lock:
            verified: Dict[str, BaseAgent] = {}
            for name in agent_names:
                current = self._get_cached_agent(user_id, name)
                if current is not None:
                    verified[name] = current

        return verified

    async def remove_user(self, user_id: str) -> bool:
        """清理指定用户的所有 Agent 实例"""
        user_lock = await self._get_user_lock(user_id)
        async with user_lock:
            removed = False
            if user_id in self._user_agents:
                agent_names = list(self._user_agents[user_id].keys())
                del self._user_agents[user_id]
                logger.info(f"移除用户 {user_id} 的 Agent 实例: {agent_names}")
                removed = True
            if user_id in self._user_coordinators:
                del self._user_coordinators[user_id]
                logger.info(f"移除用户 {user_id} 的 CoordinatorAgent")
                removed = True
        async with self._global_lock:
            if user_id in self._user_locks:
                del self._user_locks[user_id]
        return removed

    def get_agent_names(self) -> list:
        """返回所有可用的 Agent 名称"""
        return list(self._AGENT_CLASSES.keys())

    def get_user_count(self) -> int:
        """返回当前活跃用户数"""
        return len(self._user_agents)

    async def get_user_agent_names(self, user_id: str) -> list:
        """返回指定用户拥有的 Agent 名称列表"""
        user_lock = await self._get_user_lock(user_id)
        async with user_lock:
            if user_id in self._user_agents:
                return list(self._user_agents[user_id].keys())
            return []

    async def _get_user_lock(self, user_id: str) -> asyncio.Lock:
        """获取或创建用户级锁"""
        if user_id in self._user_locks:
            return self._user_locks[user_id]

        async with self._global_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = asyncio.Lock()
            return self._user_locks[user_id]

    def _get_cached_agent(self, user_id: str, agent_name: str) -> Optional[BaseAgent]:
        """无锁读取缓存的 Agent（调用方必须已持锁）"""
        if user_id in self._user_agents and agent_name in self._user_agents[user_id]:
            return self._user_agents[user_id][agent_name]
        return None

    async def _create_all_agents_parallel(
        self, user_id: str, **kwargs
    ) -> List[BaseAgent]:
        """创建所有 Agent（调用方必须已持 user_lock）"""
        agents = []
        if user_id not in self._user_agents:
            self._user_agents[user_id] = {}
        for cls in self._AGENT_CLASSES.values():
            agent = cls(**kwargs)
            self._user_agents[user_id][agent.name] = agent
            agents.append(agent)
        return agents


_default_factory: Optional[AgentFactory] = None


def get_agent_factory() -> AgentFactory:
    """获取全局单例 AgentFactory"""
    global _default_factory
    if _default_factory is None:
        _default_factory = AgentFactory()
    return _default_factory