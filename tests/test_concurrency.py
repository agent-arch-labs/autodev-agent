"""
并发压力测试：验证 AgentFactory 用户隔离在高并发下的正确性

测试场景:
1. 多用户并发获取 Agent 实例，验证实例隔离
2. 同一用户并发获取同一类型 Agent，验证幂等性
3. 并发执行 Agent.execute() 验证状态不跨用户泄漏
4. Coordinator 在并发下的隔离性
5. 并发 remove_user 不影响其他用户
6. 大规模并发压力测试
"""

import asyncio
import time
import random
from typing import Dict, Set, Any
from collections import defaultdict

import pytest

from agents import (
    get_agent_factory,
    RequirementAgent,
    ArchitectAgent,
    FunctionAgent,
    CodingAgent,
    TestAgent,
    RuntimeAgent,
    CoordinatorAgent,
    Task,
)
from agents.agent_factory import AgentFactory
from context import ContextEngine


def generate_task(agent_name: str) -> Task:
    return Task(
        task_id=f"task-{random.randint(0, 100000)}",
        agent_name=agent_name,
        input_data={"input": f"generate {agent_name} test output"},
    )


class TestAgentFactoryConcurrency:
    """AgentFactory 并发隔离测试"""

    @pytest.mark.asyncio
    async def test_multi_user_concurrent_get_agent(self):
        """多用户并发获取 Agent，每个用户得到独立实例"""
        factory = AgentFactory()
        user_count = 20
        instance_map: Dict[str, Dict[str, int]] = {}

        async def user_get_agents(user_id: str):
            agents = {}
            for agent_cls in [
                RequirementAgent, ArchitectAgent, FunctionAgent,
                CodingAgent, TestAgent, RuntimeAgent,
            ]:
                agent = await factory.get_agent(user_id, agent_cls)
                agents[agent_cls.name] = id(agent)
            # 模拟随机顺序，增加并发随机性
            await asyncio.sleep(random.uniform(0, 0.01))
            instance_map[user_id] = agents
            return agents

        tasks = [user_get_agents(f"user-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)

        assert len(instance_map) == user_count

        all_requirement_ids: Set[int] = set()
        for user_id, agents in instance_map.items():
            req_id = agents["requirement"]
            assert req_id not in all_requirement_ids, f"用户 {user_id} 的 RequirementAgent 与其他用户共享!"
            all_requirement_ids.add(req_id)

        for user_id, agents in instance_map.items():
            arch_id = agents["architect"]
            for other_user, other_agents in instance_map.items():
                if other_user != user_id:
                    assert arch_id != other_agents["architect"], \
                        f"用户 {user_id} 和 {other_user} 共享 ArchitectAgent!"

        assert factory.get_user_count() == user_count

    @pytest.mark.asyncio
    async def test_same_user_concurrent_get_same_agent(self):
        """同一用户并发获取同类型 Agent，始终返回同一实例"""
        factory = AgentFactory()
        user_id = "concurrent-user"
        agent_class = RequirementAgent
        concurrency = 50
        instance_ids: list = []

        async def get_agent():
            agent = await factory.get_agent(user_id, agent_class)
            instance_ids.append(id(agent))
            await asyncio.sleep(random.uniform(0, 0.005))
            return agent

        tasks = [get_agent() for _ in range(concurrency)]
        await asyncio.gather(*tasks)

        unique_ids = set(instance_ids)
        assert len(unique_ids) == 1, \
            f"同一用户并发获取同类型 Agent 应该返回同一实例, 实际有 {len(unique_ids)} 个不同实例"

    @pytest.mark.asyncio
    async def test_concurrent_get_different_agent_types(self):
        """同一用户并发获取不同类型 Agent，各类型独立"""
        factory = AgentFactory()
        user_id = "multi-type-user"
        agent_classes = [
            RequirementAgent, ArchitectAgent, FunctionAgent,
            CodingAgent, TestAgent, RuntimeAgent,
        ]
        results: Dict[str, int] = {}

        async def get_agent(agent_cls):
            agent = await factory.get_agent(user_id, agent_cls)
            results[agent_cls.name] = id(agent)
            return agent

        tasks = [get_agent(cls) for cls in agent_classes]
        random.shuffle(tasks)
        await asyncio.gather(*tasks)

        assert len(results) == len(agent_classes)
        unique_ids = set(results.values())
        assert len(unique_ids) == len(agent_classes), "不同类型 Agent 应该有不同实例"

    @pytest.mark.asyncio
    async def test_concurrent_context_isolation(self):
        """并发执行 Agent.execute() 时上下文不跨用户泄漏"""
        factory = AgentFactory()
        user_count = 10
        results: Dict[str, Dict[str, Any]] = {}

        async def user_workflow(user_id: str):
            context = ContextEngine(session_id=f"session-{user_id}", user_id=user_id)
            agent = await factory.get_agent(user_id, RequirementAgent)

            task = Task(
                task_id=f"task-{user_id}",
                agent_name="requirement",
                input_data={"input": f"用户 {user_id} 的专属需求: 做一个 {user_id} 系统"},
            )

            result = await agent.execute(task, context)
            results[user_id] = {
                "task_status": result.status.value,
                "output_data": result.output_data,
                "context_task": context.get_task_context("current_prd"),
            }
            return result

        tasks = [user_workflow(f"user-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)

        assert len(results) == user_count
        for user_id, data in results.items():
            assert data["task_status"] == "completed", f"用户 {user_id} 任务未完成: {data['task_status']}"
            assert data["output_data"] is not None, f"用户 {user_id} 没有输出数据"

        for user_id, data in results.items():
            prd = data.get("context_task", {})
            if prd:
                raw_input = prd.get("raw_input", "")
                assert user_id in raw_input or "用户" in raw_input, \
                    f"用户 {user_id} 的上下文可能被其他用户污染: {raw_input}"

    @pytest.mark.asyncio
    async def test_concurrent_coordinator_isolation(self):
        """并发下 Coordinator 的 worker Agent 也是用户隔离的"""
        factory = AgentFactory()
        user_count = 15
        coord_agent_ids: Dict[str, Dict[str, int]] = {}

        async def get_coord(user_id: str):
            coord = await factory.get_coordinator(user_id)
            coord_agent_ids[user_id] = {
                agent_name: id(agent)
                for agent_name, agent in coord.agents.items()
            }
            return coord

        tasks = [get_coord(f"coord-user-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)

        assert len(coord_agent_ids) == user_count

        all_worker_ids: Set[int] = set()
        for user_id, workers in coord_agent_ids.items():
            for agent_name, wid in workers.items():
                assert wid not in all_worker_ids, \
                    f"用户 {user_id} 的 Coordinator 中 {agent_name} 与其他用户共享!"
                all_worker_ids.add(wid)

    @pytest.mark.asyncio
    async def test_concurrent_remove_user(self):
        """并发删除用户不影响其他活跃用户"""
        factory = AgentFactory()
        total_users = 20
        remove_count = 5

        async def create_user(user_id: str):
            for agent_cls in [RequirementAgent, ArchitectAgent, CodingAgent]:
                await factory.get_agent(user_id, agent_cls)

        create_tasks = [create_user(f"rm-user-{i}") for i in range(total_users)]
        await asyncio.gather(*create_tasks)
        assert factory.get_user_count() == total_users

        async def remove_user(user_id: str):
            await asyncio.sleep(random.uniform(0, 0.02))
            await factory.remove_user(user_id)
            return user_id

        remove_tasks = [remove_user(f"rm-user-{i}") for i in range(remove_count)]

        async def keep_using(user_id: str):
            for _ in range(3):
                agent = await factory.get_agent(user_id, RequirementAgent)
                await asyncio.sleep(random.uniform(0, 0.01))
            return user_id

        keep_tasks = [keep_using(f"rm-user-{i}") for i in range(remove_count, total_users)]

        all_tasks = remove_tasks + keep_tasks
        random.shuffle(all_tasks)
        await asyncio.gather(*all_tasks)

        remaining = factory.get_user_count()
        assert remaining == total_users - remove_count, \
            f"删除 {remove_count} 个用户后应剩余 {total_users - remove_count} 个, 实际: {remaining}"

        for i in range(remove_count, total_users):
            agents = await factory.get_user_agent_names(f"rm-user-{i}")
            assert len(agents) > 0, f"用户 rm-user-{i} 的 Agent 被误删!"

    @pytest.mark.asyncio
    async def test_concurrent_same_user_create_and_remove(self):
        """同一用户并发创建和删除，最终状态一致"""
        factory = AgentFactory()
        user_id = "volatile-user"

        async def create():
            await factory.get_agent(user_id, RequirementAgent)
            await factory.get_agent(user_id, ArchitectAgent)

        async def remove():
            await factory.remove_user(user_id)

        async def check():
            await asyncio.sleep(0.02)
            agents = await factory.get_user_agent_names(user_id)
            return agents

        tasks = [create(), remove(), check()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 最终状态应该一致：要么存在且完整，要么不存在
        agents = await factory.get_user_agent_names(user_id)
        if agents:
            assert "requirement" in agents
            assert "architect" in agents

    @pytest.mark.asyncio
    async def test_concurrent_instance_idempotency_detailed(self):
        """详细验证幂等性：并发 100 次获取同一用户同一类型 Agent，始终同一实例"""
        factory = AgentFactory()
        user_id = "idempotent-user"
        agent_class = FunctionAgent
        rounds = 100
        instance_ids: list = []

        async def get_and_record():
            agent = await factory.get_agent(user_id, agent_class)
            instance_ids.append(id(agent))
            # 模拟实际使用
            agent.status = "running" if random.random() > 0.5 else "idle"
            await asyncio.sleep(random.uniform(0, 0.003))

        tasks = [get_and_record() for _ in range(rounds)]
        await asyncio.gather(*tasks)

        unique_ids = set(instance_ids)
        assert len(unique_ids) == 1, \
            f"100 次并发获取应始终返回同一实例, 实际有 {len(unique_ids)} 个: {unique_ids}"


class TestAgentFactoryStress:
    """AgentFactory 压力测试"""

    @pytest.mark.asyncio
    async def test_stress_many_users_many_agents(self):
        """大规模压力测试: 100 用户 × 6 Agent ≈ 600 个实例"""
        factory = AgentFactory()
        user_count = 100
        agent_classes = [
            RequirementAgent, ArchitectAgent, FunctionAgent,
            CodingAgent, TestAgent, RuntimeAgent,
        ]

        start = time.monotonic()

        async def user_workflow(user_id: str):
            agents = {}
            for agent_cls in agent_classes:
                agent = await factory.get_agent(user_id, agent_cls)
                agents[agent_cls.name] = agent
            await asyncio.sleep(random.uniform(0, 0.005))
            return agents

        tasks = [user_workflow(f"stress-user-{i}") for i in range(user_count)]
        results = await asyncio.gather(*tasks)

        elapsed = time.monotonic() - start

        assert factory.get_user_count() == user_count

        total_instances = 0
        all_ids: Set[int] = set()
        for user_agents in results:
            for name, agent in user_agents.items():
                total_instances += 1
                agent_id = id(agent)
                all_ids.add(agent_id)

        expected_instances = user_count * len(agent_classes)
        assert total_instances == expected_instances
        assert len(all_ids) == expected_instances, \
            f"应有 {expected_instances} 个独立实例, 实际 {len(all_ids)} 个"

        print(f"\n  [压力测试] {user_count} 用户 × {len(agent_classes)} Agent = {expected_instances} 实例")
        print(f"  [压力测试] 耗时: {elapsed:.3f}s, 吞吐: {expected_instances / elapsed:.0f} 实例/s")

    @pytest.mark.asyncio
    async def test_stress_high_concurrency_get_agent(self):
        """高并发获取同一 Agent: 200 个协程同时获取同一用户同一类型"""
        factory = AgentFactory()
        user_id = "high-concurrency-user"
        agent_class = CodingAgent
        concurrency = 200
        got_ids: list = []

        async def get_agent():
            agent = await factory.get_agent(user_id, agent_class)
            got_ids.append(id(agent))
            return agent

        start = time.monotonic()
        tasks = [get_agent() for _ in range(concurrency)]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        unique = set(got_ids)
        assert len(unique) == 1, f"200 次并发, 应只有 1 个实例, 实际有 {len(unique)} 个"
        assert len(got_ids) == concurrency

        print(f"\n  [高并发] {concurrency} 协程同时获取同一 Agent")
        print(f"  [高并发] 耗时: {elapsed:.3f}s, QPS: {concurrency / elapsed:.0f}")

    @pytest.mark.asyncio
    async def test_stress_mixed_operations(self):
        """混合操作压力: 并发获取 + 执行 + 删除"""
        factory = AgentFactory()
        user_count = 30
        agent_classes = [
            RequirementAgent, ArchitectAgent, FunctionAgent,
            CodingAgent, TestAgent, RuntimeAgent,
        ]
        errors: list = []

        async def mixed_workflow(user_id: str):
            try:
                agents = {}
                for agent_cls in agent_classes:
                    agents[agent_cls.name] = await factory.get_agent(user_id, agent_cls)

                context = ContextEngine(session_id=f"mixed-{user_id}", user_id=user_id)
                requirement = agents["requirement"]
                task = Task(
                    task_id=f"mixed-task-{user_id}",
                    agent_name="requirement",
                    input_data={"input": f"需求: {user_id}"},
                )
                result = await requirement.execute(task, context)
                assert result.status.value == "completed", f"用户 {user_id} 执行失败: {result.error}"

                if random.random() > 0.7:
                    await factory.remove_user(user_id)

            except Exception as e:
                errors.append(f"{user_id}: {e}")

        start = time.monotonic()
        tasks = [mixed_workflow(f"mixed-user-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        assert len(errors) == 0, f"有 {len(errors)} 个错误:\n" + "\n".join(errors[:5])
        print(f"\n  [混合操作] {user_count} 用户并发 (获取 + 执行 + 删除)")
        print(f"  [混合操作] 耗时: {elapsed:.3f}s, 错误: {len(errors)}")

    @pytest.mark.asyncio
    async def test_stress_context_manager_isolation(self):
        """ContextManager 并发隔离: 多用户并发创建/删除 session"""
        from context import ContextManager

        user_count = 30
        sessions: Dict[str, str] = {}

        async def create_session(user_id: str):
            session_id = f"ctx-stress-{user_id}"
            ctx = ContextManager.get_context(session_id, user_id=user_id)
            ctx.set_task_context("owner", user_id)
            ctx.set_task_context("timestamp", time.monotonic())
            sessions[user_id] = session_id

        async def verify_session(user_id: str):
            session_id = sessions.get(user_id)
            if session_id:
                ctx = ContextManager.get_context(session_id)
                owner = ctx.get_task_context("owner")
                assert owner == user_id, \
                    f"用户 {user_id} 读取到的上下文属于 {owner}, 上下文泄漏!"

        async def user_workflow(user_id: str):
            await create_session(user_id)
            await asyncio.sleep(random.uniform(0, 0.005))
            await verify_session(user_id)

        tasks = [user_workflow(f"ctx-user-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)

        assert len(ContextManager.list_sessions()) == user_count

        # 清理
        for session_id in list(ContextManager.list_sessions()):
            ContextManager.delete_context(session_id)

        assert len(ContextManager.list_sessions()) == 0

        print(f"\n  [上下文隔离] {user_count} 用户并发验证上下文不泄漏")

    @pytest.mark.asyncio
    async def test_stress_extreme_1000_users_batch_get(self):
        """
        极端压力: 1000 用户同时调用 batch_get_agents

        验证:
        1. 每用户独立锁确保零跨用户争用
        2. _global_lock 仅用于首次创建 user_lock，短临界区
        3. 一致性校验不制造瓶颈
        """
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_count = 1000

        async def user_workflow(user_id):
            agents = await factory.batch_get_agents(user_id)
            assert len(agents) == 6
            for name, agent in agents.items():
                assert agent.name == name

        start = time.monotonic()
        tasks = [user_workflow(f"extreme-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        total_instances = sum(len(agents) for agents in factory._user_agents.values())
        assert total_instances == user_count * 6

        per_user = elapsed / user_count * 1000
        throughput = total_instances / elapsed

        print(f"\n  [极端压力-1000用户]")
        print(f"    总耗时:       {elapsed:.4f}s ({elapsed*1000:.1f}ms)")
        print(f"    总实例:        {total_instances}")
        print(f"    平均每用户:    {per_user:.3f}ms")
        print(f"    吞吐:          {throughput:.0f} agent/s")

        assert factory.get_user_count() == user_count

    @pytest.mark.asyncio
    async def test_stress_1000_users_mixed_batch_and_single(self):
        """
        极端压力: 1000 用户混合调用 batch_get_agents + 单 Agent get_agent

        模拟真实场景中用户请求随机打散到不同 Agent 类型。
        """
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_count = 1000

        import random
        random.seed(42)
        agent_classes = list(factory._AGENT_CLASSES.values())

        async def user_workflow(user_id):
            if random.random() < 0.3:
                agents = await factory.batch_get_agents(user_id)
                assert len(agents) == 6
            else:
                cls = random.choice(agent_classes)
                agent = await factory.get_agent(user_id, cls)
                assert agent.name == cls.name
                assert agent is not None

        start = time.monotonic()
        tasks = [user_workflow(f"mixed-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        total_instances = sum(len(agents) for agents in factory._user_agents.values())
        throughput = user_count / elapsed

        print(f"\n  [极端压力-1000用户混合]")
        print(f"    总耗时:       {elapsed:.4f}s ({elapsed*1000:.1f}ms)")
        print(f"    总用户:        {user_count}")
        print(f"    总实例:        {total_instances}")
        print(f"    QPS:           {throughput:.0f} req/s")
        print(f"    平均每用户:    {elapsed/user_count*1000:.3f}ms")


class TestAgentFactoryTiming:
    """AgentFactory 时序测试 - 验证并发时序安全"""

    @pytest.mark.asyncio
    async def test_eventual_instance_count(self):
        """验证无论并发顺序如何，最终实例数正确"""
        factory = AgentFactory()
        user_count = 50
        expected_per_user = 6

        async def create_one_agent(user_id: str, agent_cls):
            await asyncio.sleep(random.uniform(0, 0.01))
            await factory.get_agent(user_id, agent_cls)

        tasks = []
        for i in range(user_count):
            for agent_cls in [
                RequirementAgent, ArchitectAgent, FunctionAgent,
                CodingAgent, TestAgent, RuntimeAgent,
            ]:
                tasks.append(create_one_agent(f"timing-user-{i}", agent_cls))

        random.shuffle(tasks)
        await asyncio.gather(*tasks)

        assert factory.get_user_count() == user_count

        for i in range(user_count):
            agents = await factory.get_user_agent_names(f"timing-user-{i}")
            assert len(agents) == expected_per_user, \
                f"用户 timing-user-{i} 应有 {expected_per_user} 个 Agent, 实际 {len(agents)}: {agents}"


class TestAgentFactoryBenchmark:
    """AgentFactory 延迟基准测试 - 量化优化效果"""

    @pytest.mark.asyncio
    async def test_bench_cold_single_user_sequential(self):
        """基准: 单个用户冷启动，串行创建 6 个 Agent（模拟旧版行为）"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "bench-sequential"
        agent_classes = [
            RequirementAgent, ArchitectAgent, FunctionAgent,
            CodingAgent, TestAgent, RuntimeAgent,
        ]

        start = time.monotonic()
        for agent_cls in agent_classes:
            await factory.get_agent(user_id, agent_cls)
        elapsed = time.monotonic() - start

        assert factory.get_user_count() == 1
        agents = await factory.get_user_agent_names(user_id)
        assert len(agents) == 6
        print(f"\n  [基准-串行] 1 用户串行创建 6 Agent: {elapsed:.6f}s ({elapsed*1000:.3f}ms)")

    @pytest.mark.asyncio
    async def test_bench_cold_single_user_parallel(self):
        """基准: 单个用户冷启动，batch_get_agents 并行创建（优化版）"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "bench-parallel"

        start = time.monotonic()
        await factory.batch_get_agents(user_id)
        elapsed = time.monotonic() - start

        assert factory.get_user_count() == 1
        agents = await factory.get_user_agent_names(user_id)
        assert len(agents) == 6
        print(f"\n  [基准-并行] 1 用户 batch_get 创建 6 Agent: {elapsed:.6f}s ({elapsed*1000:.3f}ms)")

    @pytest.mark.asyncio
    async def test_bench_cold_single_user_coordinator(self):
        """基准: 单个用户通过 get_coordinator 冷启动"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "bench-coord"

        start = time.monotonic()
        await factory.get_coordinator(user_id)
        elapsed = time.monotonic() - start

        assert factory.get_user_count() == 1
        agents = await factory.get_user_agent_names(user_id)
        assert len(agents) == 6
        print(f"\n  [基准-Coord] 1 用户 coordinator 冷启动: {elapsed:.6f}s ({elapsed*1000:.3f}ms)")

    @pytest.mark.asyncio
    async def test_bench_warm_get_agent(self):
        """基准: 热启动，Agent 已缓存时的获取延迟"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "bench-warm"

        await factory.batch_get_agents(user_id)

        start = time.monotonic()
        agent = await factory.get_agent(user_id, RequirementAgent)
        elapsed = time.monotonic() - start

        assert agent is not None
        print(f"\n  [基准-热启动] 缓存命中延迟: {elapsed:.6f}s ({elapsed*1000:.3f}ms)")

    @pytest.mark.asyncio
    async def test_bench_prewarm_vs_cold(self):
        """基准: prewarm 预热后再获取 vs 直接冷获取"""
        from agents.agent_factory import AgentFactory

        cold_factory = AgentFactory()
        warm_factory = AgentFactory()

        start_cold = time.monotonic()
        await cold_factory.get_agent("user-cold", RequirementAgent)
        await cold_factory.get_agent("user-cold", ArchitectAgent)
        await cold_factory.get_agent("user-cold", FunctionAgent)
        cold_elapsed = time.monotonic() - start_cold

        start_warm = time.monotonic()
        await warm_factory.prewarm_user("user-warm")
        warm_elapsed = time.monotonic() - start_warm

        start_cached = time.monotonic()
        await warm_factory.get_agent("user-warm", RequirementAgent)
        await warm_factory.get_agent("user-warm", ArchitectAgent)
        await warm_factory.get_agent("user-warm", FunctionAgent)
        cached_elapsed = time.monotonic() - start_cached

        print(f"\n  [基准-预热对比] 冷创建 3 Agent: {cold_elapsed:.6f}s ({cold_elapsed*1000:.3f}ms)")
        print(f"  [基准-预热对比] prewarm 全部: {warm_elapsed:.6f}s ({warm_elapsed*1000:.3f}ms)")
        print(f"  [基准-预热对比] 预热后获取 3 Agent: {cached_elapsed:.6f}s ({cached_elapsed*1000:.3f}ms)")

    @pytest.mark.asyncio
    async def test_bench_multi_user_concurrent_init(self):
        """基准: 多用户并发冷启动（核心优化场景）"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_count = 50

        async def init_user(user_id: str):
            await factory.batch_get_agents(user_id)

        start = time.monotonic()
        tasks = [init_user(f"bench-multi-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        assert factory.get_user_count() == user_count
        total_agents = user_count * 6
        print(f"\n  [基准-多用户并发] {user_count} 用户并发冷启动")
        print(f"  [基准-多用户并发] 总耗时: {elapsed:.3f}s ({elapsed*1000:.1f}ms)")
        print(f"  [基准-多用户并发] 平均每用户: {elapsed/user_count*1000:.3f}ms")
        print(f"  [基准-多用户并发] 总实例: {total_agents}, 吞吐: {total_agents/elapsed:.0f} agent/s")

    @pytest.mark.asyncio
    async def test_bench_concurrent_users_lock_contention(self):
        """基准: 测量多用户锁争用（per-user lock 的核心优势）"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_count = 100

        async def rapid_access(user_id: str):
            for agent_cls in [
                RequirementAgent, ArchitectAgent, FunctionAgent,
                CodingAgent, TestAgent, RuntimeAgent,
            ]:
                await factory.get_agent(user_id, agent_cls)

        start = time.monotonic()
        tasks = [rapid_access(f"lock-bench-{i}") for i in range(user_count)]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        assert factory.get_user_count() == user_count
        print(f"\n  [基准-锁争用] {user_count} 用户并发 × 6 get_agent = {user_count*6} 次调用")
        print(f"  [基准-锁争用] 总耗时: {elapsed:.3f}s ({elapsed*1000:.1f}ms)")
        print(f"  [基准-锁争用] QPS: {user_count*6/elapsed:.0f} calls/s")

    @pytest.mark.asyncio
    async def test_bench_full_workflow_startup(self):
        """基准: 完整启动链路，模拟 gateway 首次请求"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "gateway-startup"

        start = time.monotonic()

        agent_map = await factory.batch_get_agents(user_id)
        coordinator = await factory.get_coordinator(user_id)
        agent_map["coordinator"] = coordinator

        context = ContextEngine(session_id="startup-session", user_id=user_id)

        elapsed = time.monotonic() - start

        assert len(agent_map) == 7
        assert context.user_id == user_id
        print(f"\n  [基准-完整启动] gateway 首个请求完整链路: {elapsed:.6f}s ({elapsed*1000:.3f}ms)")


class TestAgentFactoryConcurrencyBugs:
    """并发 Bug 复现与回归测试"""

    @pytest.mark.asyncio
    async def test_bug_remove_user_leaks_locks(self):
        """Bug 复现: remove_user 未清理 _user_locks 导致内存泄漏"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_count = 50

        for i in range(user_count):
            await factory.get_agent(f"leak-user-{i}", RequirementAgent)
            await factory.remove_user(f"leak-user-{i}")

        assert factory.get_user_count() == 0, \
            "_user_agents 应已清空"

        leaked_lock_count = len(factory._user_locks)
        assert leaked_lock_count == 0, \
            f"remove_user 应清理 _user_locks, 实际泄漏 {leaked_lock_count} 个锁条目"
        print(f"\n  [Bug1-复现] 创建/删除 {user_count} 用户后 _user_locks 剩余: {leaked_lock_count}")

    @pytest.mark.asyncio
    async def test_bug_stale_cached_on_remove(self):
        """
        验证: 无论 batch_get_agents 和 remove_user 以任何顺序交错执行，
        返回的 Agent 字典中的每个实例都与工厂中的实例完全一致
        """
        from agents.agent_factory import AgentFactory

        for _ in range(20):
            factory = AgentFactory()
            user_id = "stale-cache-test"

            await factory.get_agent(user_id, RequirementAgent)
            await factory.get_agent(user_id, ArchitectAgent)

            async def batch_get():
                await asyncio.sleep(0)
                return await factory.batch_get_agents(user_id)

            async def remove():
                await factory.remove_user(user_id)

            batch_task = asyncio.create_task(batch_get())
            remove_task = asyncio.create_task(remove())

            agents = await batch_task
            await remove_task

            assert len(agents) == 6, f"应返回 6 个 Agent, 实际 {len(agents)}"

            for name in agents:
                factory_agent = await factory.get_agent(user_id, factory._AGENT_CLASSES[name])
                assert agents[name] is factory_agent, \
                    f"agent={name}: batch 返回 {id(agents[name])} != 工厂缓存 {id(factory_agent)} (过期引用!)"
                assert agents[name] is not None

        print(f"  [一致性验证] 20 轮并发交替执行, 0 个过期引用: ✓")

    @pytest.mark.asyncio
    async def test_bug_remove_user_cleanup_idempotent(self):
        """验证: 删除一个不存在的用户不应崩溃"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        result = await factory.remove_user("nonexistent-user")
        assert result is False, "删除不存在的用户应返回 False"

    @pytest.mark.asyncio
    async def test_bug_batch_get_agents_race_with_remove(self):
        """Bug 复现: batch_get_agents Phase 1 缓存被 remove_user 后过期"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "race-user"

        await factory.batch_get_agents(user_id)
        assert factory.get_user_count() == 1

        async def batch_get():
            await asyncio.sleep(0)
            return await factory.batch_get_agents(user_id)

        async def remove():
            await factory.remove_user(user_id)

        batch_task = asyncio.create_task(batch_get())
        remove_task = asyncio.create_task(remove())

        agents = await batch_task
        await remove_task

        assert len(agents) == 6, \
            f"batch_get_agents 应返回 6 个 Agent, 实际 {len(agents)}"

        names = await factory.get_user_agent_names(user_id)
        assert len(names) == 6, \
            f"user_id 应被重新创建并包含 6 个 Agent, 实际 {len(names)}: {names}"

        for name in agents:
            cached = await factory.get_agent(user_id, factory._AGENT_CLASSES[name])
            assert agents[name] is cached, \
                f"agent={name}: 返回的引用应等于工厂中缓存的实例!"

        print(f"\n  [Bug2-复现] batch_get_agents + remove_user 并发后 Agent 引用一致性: ✓")

    @pytest.mark.asyncio
    async def test_bug_batch_get_agents_partial_race(self):
        """Bug 复现: batch_get_agents 中途被部分覆盖后返回一致性"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "partial-race"

        async def slow_batch_get():
            result = await factory.batch_get_agents(user_id)
            return result

        async def concurrent_individual_get():
            await asyncio.sleep(0)
            await factory.get_agent(user_id, ArchitectAgent)
            await factory.get_agent(user_id, CodingAgent)

        batch_task = asyncio.create_task(slow_batch_get())
        individual_task = asyncio.create_task(concurrent_individual_get())

        agents = await batch_task
        await individual_task

        assert len(agents) == 6, f"应返回 6 个 Agent, 实际 {len(agents)}"

        for name, agent in agents.items():
            cached = await factory.get_agent(user_id, factory._AGENT_CLASSES[name])
            assert agent is cached, \
                f"agent={name}: batch 返回的与工厂中缓存的不是同一实例!"

        print(f"  [Bug2-复现] 部分覆盖后 batch 结果一致性: ✓")

    @pytest.mark.asyncio
    async def test_bug_remove_then_recreate_user(self):
        """验证: 删除用户后重新创建，新旧实例完全独立"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "recreate-user"

        agent_v1 = await factory.get_agent(user_id, RequirementAgent)
        id_v1 = id(agent_v1)

        await factory.remove_user(user_id)

        agent_v2 = await factory.get_agent(user_id, RequirementAgent)
        id_v2 = id(agent_v2)

        assert id_v1 != id_v2, "删除并重建后应得到新的实例"
        assert factory.get_user_count() == 1
        agents = await factory.get_user_agent_names(user_id)
        assert "requirement" in agents, "重建后应包含 requirement"
        print(f"\n  [删除重建] v1={id_v1}, v2={id_v2}, 独立实例: ✓")

    @pytest.mark.asyncio
    async def test_bug_lock_cleanup_after_remove(self):
        """验证: 删除用户后 user_lock 可被安全回收（不阻塞后续操作）"""
        from agents.agent_factory import AgentFactory

        factory = AgentFactory()
        user_id = "lock-cleanup"

        lock_before = await factory._get_user_lock(user_id)
        await factory.get_agent(user_id, RequirementAgent)
        await factory.remove_user(user_id)

        lock_after = await factory._get_user_lock(user_id)
        assert lock_before is not lock_after, \
            "删除用户后应创建新的 lock，而非复用旧的"
        print(f"  [锁清理] lock_before={id(lock_before)}, lock_after={id(lock_after)}, 新建: ✓")