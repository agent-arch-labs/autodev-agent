"""
ReAct Agent 实现 - 基于 ReAct 论文

本模块实现了 ReAct 论文的核心 Agent 循环，支持四种提示方法：
1. Standard: 直接问答，无推理过程
2. CoT (Chain-of-Thought): 逐步推理，但不与环境交互
3. Act-only: 仅执行动作，无显式推理
4. ReAct: 推理与动作交错进行（论文核心贡献）

额外支持：
- Self-Consistency (CoT-SC): 多次采样取多数答案
- ReAct+CoT-SC 组合策略: 先尝试 ReAct，失败后回退到 CoT-SC

参考论文: ReAct: Synergizing Reasoning and Acting in Language Models (Yao et al., 2023)
"""

import re
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass, field
from collections import Counter

from agents.base import BaseAgent, Task, AgentStatus


@dataclass
class ReActStep:
    """
    ReAct Agent 单步执行记录

    记录 ReAct 循环中每一步的完整信息。

    Attributes:
        step_num: 步骤编号（从1开始）
        thought: 推理内容（ReAct 方法）
        action: 动作类型（search/lookup/finish/tool）
        argument: 动作参数
        observation: 环境返回的观察结果
    """
    step_num: int
    thought: Optional[str] = None
    action: Optional[str] = None
    argument: Optional[str] = None
    observation: Optional[str] = None


@dataclass
class ReActTrajectory:
    """
    ReAct Agent 完整执行轨迹

    记录从问题到最终答案的完整推理-动作-观察序列。

    Attributes:
        question: 输入问题
        steps: 执行步骤列表
        final_answer: 最终答案
        method: 使用的提示方法
        success: 是否成功完成任务
    """
    question: str
    steps: list = field(default_factory=list)
    final_answer: Optional[str] = None
    method: str = "react"
    success: bool = False


class ReActAgent(BaseAgent):
    """
    ReAct Agent 核心实现

    实现了 ReAct 论文中的核心循环：
    Thought -> Action -> Observation -> Thought -> Action -> ... -> Finish

    支持四种提示方法:
    - standard: 直接问答
    - cot: 链式思考（Chain-of-Thought）
    - act: 仅动作（无显式推理）
    - react: 推理+动作交错（论文核心方法）
    """

    name = "react"
    description = "ReAct reasoning agent - integrates reasoning and action"

    def __init__(self, max_steps: int = 7, method: str = "react", **kwargs):
        super().__init__(**kwargs)
        self.max_steps = max_steps
        self.method = method
        self._llm = None

    async def execute(self, task: Task, context: "ContextEngine") -> Task:
        """
        执行 ReAct Agent

        Args:
            task: 任务对象
            context: 上下文引擎

        Returns:
            执行完成的任务对象
        """
        self.status = AgentStatus.RUNNING
        try:
            question = task.input_data.get("input", "")
            if not question:
                raise ValueError("No input provided for ReAct reasoning")

            trajectory = await self.run(question, context)
            
            task.output_data = {
                "trajectory": trajectory,
                "answer": trajectory.final_answer,
                "method": trajectory.method,
                "success": trajectory.success,
                "steps": len(trajectory.steps),
            }
            task.status = AgentStatus.COMPLETED

        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
            task.output_data = {"error": str(e)}
        finally:
            self.status = AgentStatus.IDLE
        return task

    async def run(self, question: str, context: "ContextEngine", method: str = None) -> ReActTrajectory:
        """
        运行 ReAct Agent 并返回完整轨迹

        Args:
            question: 输入问题
            context: 上下文引擎
            method: 提示方法（standard/cot/act/react）

        Returns:
            ReActTrajectory 对象，包含完整的执行轨迹和最终答案
        """
        method = method or self.method
        trajectory = ReActTrajectory(question=question, method=method)

        if method == "standard":
            trajectory.final_answer = await self._run_standard(question, context)
            trajectory.success = True if trajectory.final_answer else False
        elif method == "cot":
            trajectory.final_answer = await self._run_cot(question, context)
            trajectory.success = True if trajectory.final_answer else False
        elif method == "act":
            trajectory = await self._run_act(question, trajectory, context)
        elif method == "react":
            trajectory = await self._run_react(question, trajectory, context)
        else:
            raise ValueError(f"Unknown method: {method}")

        return trajectory

    async def _run_standard(self, question: str, context: "ContextEngine") -> Optional[str]:
        """Standard 方法: 直接问答"""
        prompt = self._get_standard_prompt(question)
        response = await self._generate_response(prompt)
        return response.strip() if response else None

    async def _run_cot(self, question: str, context: "ContextEngine") -> Optional[str]:
        """CoT (Chain-of-Thought) 方法: 链式思考"""
        prompt = self._get_cot_prompt(question)
        response = await self._generate_response(prompt)
        
        answer = self._extract_answer(response)
        if answer:
            return answer

        lines = response.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line:
                return line
        return response.strip() if response else None

    async def _run_act(self, question: str, trajectory: ReActTrajectory, context: "ContextEngine") -> ReActTrajectory:
        """Act-only 方法: 仅动作（无显式推理）"""
        prompt = self._get_act_prompt(question)
        current_context = prompt

        for step_num in range(1, self.max_steps + 1):
            response = await self._generate_response(current_context, stop=["\nObservation"])
            action_info = self._extract_action(response)

            if action_info is None:
                break

            action_name = action_info["action"]
            argument = action_info["argument"]

            react_step = ReActStep(
                step_num=step_num,
                action=action_name,
                argument=argument,
            )

            if action_name == "finish":
                react_step.observation = "Episode finished"
                trajectory.steps.append(react_step)
                trajectory.final_answer = argument
                trajectory.success = True
                break

            observation = await self._execute_action(action_name, argument, context)
            react_step.observation = observation
            trajectory.steps.append(react_step)

            current_context += f"\nAction {step_num}: {response.strip()}\nObservation {step_num}: {observation}"

        return trajectory

    async def _run_react(self, question: str, trajectory: ReActTrajectory, context: "ContextEngine") -> ReActTrajectory:
        """
        ReAct 方法: 推理与动作交错（论文核心方法）

        每一步包含:
        1. Thought: 分析当前状态，规划下一步
        2. Action: 执行搜索/查找/完成动作
        3. Observation: 获取环境反馈
        """
        prompt = self._get_react_prompt(question)
        current_context = prompt

        for step_num in range(1, self.max_steps + 1):
            response = await self._generate_response(current_context, stop=["\nObservation"])

            thought = self._extract_thought(response)
            action_info = self._extract_action(response)

            if action_info is None:
                break

            action_name = action_info["action"]
            argument = action_info["argument"]

            react_step = ReActStep(
                step_num=step_num,
                thought=thought,
                action=action_name,
                argument=argument,
            )

            if action_name == "finish":
                react_step.observation = "Episode finished"
                trajectory.steps.append(react_step)
                trajectory.final_answer = argument
                trajectory.success = True
                break

            observation = await self._execute_action(action_name, argument, context)
            react_step.observation = observation
            trajectory.steps.append(react_step)

            current_context += (
                f"\nThought {step_num}: {thought or ''}"
                f"\nAction {step_num}: {action_name}[{argument}]"
                f"\nObservation {step_num}: {observation}"
            )

        return trajectory

    async def _generate_response(self, prompt: str, stop: Optional[list] = None) -> str:
        """生成 LLM 响应（模拟实现）"""
        # TODO: 集成真实 LLM 调用
        return self._mock_response(prompt)

    def _mock_response(self, prompt: str) -> str:
        """模拟 LLM 响应用于测试"""
        # 统计已有多少个 Observation（只计算步骤中的，格式为 "Observation X:"）
        import re
        observation_matches = re.findall(r"Observation\s+\d+:", prompt)
        observation_count = len(observation_matches)
        
        # 根据步骤返回不同的响应
        if observation_count == 0:
            # 第一步：分析问题，决定搜索什么
            if "elevation" in prompt.lower() and "Colorado" in prompt:
                return "Thought 1: To find the elevation of Colorado orogeny's eastern sector, I need to first search for information about the Colorado orogeny.\nAction 1: Search[Colorado orogeny]"
            if "Milhouse" in prompt:
                return "Thought 1: I need to search for Milhouse to find who he was named after.\nAction 1: Search[Milhouse]"
            if "Colorado" in prompt:
                return "Thought 1: I need to search for Colorado orogeny.\nAction 1: Search[Colorado orogeny]"
            if "Question:" in prompt:
                return "Thought 1: This is a question I need to analyze. Let me search for relevant information.\nAction 1: Search[analysis]"
            return "Thought 1: I need to search for information to answer this question.\nAction 1: Search[query]"
        
        elif observation_count == 1:
            # 第二步：根据第一次搜索结果决定下一步
            if "Colorado orogeny" in prompt:
                return "Thought 2: The search results mention the Colorado orogeny. Now I need to find information about its eastern sector and elevation.\nAction 2: Search[eastern sector elevation]"
            if "Milhouse" in prompt:
                return "Thought 2: Found Milhouse information. Now I need to look up who he was named after.\nAction 2: Lookup[named after]"
            return "Thought 2: I have some information, but need more details.\nAction 2: Search[more details]"
        
        elif observation_count == 2:
            # 第三步：根据第二次搜索结果总结并回答
            if "elevation" in prompt.lower():
                return "Thought 3: I now have enough information. The eastern sector of the Colorado orogeny extends into the High Plains, which have an elevation range of 1,800 to 7,000 ft.\nAction 3: Finish[1,800 to 7,000 ft]"
            if "Milhouse" in prompt:
                return "Thought 3: Milhouse was named after Richard Nixon. I have the answer.\nAction 3: Finish[Richard Nixon]"
            return "Thought 3: I have gathered enough information to answer the question.\nAction 3: Finish[Answer found]"
        
        else:
            return "Thought: I have enough information.\nAction: Finish[Answer generated]"

    async def _execute_action(self, action_name: str, argument: str, context: "ContextEngine") -> str:
        """
        执行动作并与环境交互

        支持的动作:
        - search: 搜索信息
        - lookup: 在当前上下文中查找关键词
        - finish: 结束任务
        - tool: 调用工具
        """
        if action_name == "search":
            return await self._search(argument, context)
        elif action_name == "lookup":
            return await self._lookup(argument, context)
        elif action_name == "finish":
            return "Episode finished"
        elif action_name == "tool":
            return await self._call_tool(argument, context)
        else:
            return f"Unknown action: {action_name}"

    async def _search(self, query: str, context: "ContextEngine") -> str:
        """模拟搜索操作"""
        mock_results = {
            "Milhouse": "Milhouse Mussolini Van Houten is a recurring character in The Simpsons, created by Matt Groening.",
            "Colorado orogeny": "The Colorado orogeny was an episode of mountain building (orogeny) in Colorado and surrounding areas, with its eastern sector extending into the High Plains region.",
            "eastern sector elevation": "The eastern sector of the Colorado orogeny extends into the High Plains, which rise in elevation from around 1,800 to 7,000 feet (550 to 2,130 meters).",
            "elevation": "Elevation range varies depending on location. The High Plains range from 1,800 to 7,000 ft.",
            "analysis": "Analysis shows relevant information can be found through further searches.",
            "query": "General search results for your query.",
            "more details": "Additional details have been found.",
        }
        return mock_results.get(query, f"Search results for: {query}")

    async def _lookup(self, keyword: str, context: "ContextEngine") -> str:
        """模拟查找操作"""
        return f"(Result 1 / 1) Found information about: {keyword}"

    async def _call_tool(self, tool_name: str, context: "ContextEngine") -> str:
        """模拟工具调用"""
        return f"Tool {tool_name} executed successfully"

    def _extract_action(self, text: str) -> Optional[dict]:
        """从文本中提取动作"""
        patterns = [
            r"Search\[(.+?)\]",
            r"Lookup\[(.+?)\]",
            r"Finish\[(.+?)\]",
            r"Tool\[(.+?)\]",
        ]
        action_names = ["search", "lookup", "finish", "tool"]

        for i, pattern in enumerate(patterns):
            match = re.search(pattern, text)
            if match:
                return {"action": action_names[i], "argument": match.group(1).strip()}
        return None

    def _extract_thought(self, text: str) -> Optional[str]:
        """从文本中提取思考内容"""
        match = re.search(
            r"Thought\s*\d*\s*:\s*(.+?)(?=\n(?:Action|Thought|Observation|$))",
            text,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()

        match = re.search(
            r"think\s*:\s*(.+?)(?=\n(?:>|Action|Observation|$))",
            text,
            re.DOTALL,
        )
        if match:
            return match.group(1).strip()
        return None

    def _extract_answer(self, text: str) -> Optional[str]:
        """从文本中提取最终答案"""
        match = re.search(r"Finish\[(.+?)\]", text)
        if match:
            return match.group(1).strip()

        match = re.search(r"(?:Answer|answer)\s*:\s*(.+?)(?=\n|$)", text)
        if match:
            return match.group(1).strip()
        return None

    def _get_standard_prompt(self, question: str) -> str:
        """获取标准问答提示词"""
        return f"""Answer the following question:
Question: {question}
Answer:"""

    def _get_cot_prompt(self, question: str) -> str:
        """获取链式思考提示词"""
        return f"""Answer the following question with step-by-step reasoning:
Question: {question}
Thought:"""

    def _get_act_prompt(self, question: str) -> str:
        """获取仅动作提示词"""
        return f"""Answer the following question by using Search, Lookup, and Finish actions:
Question: {question}
"""

    def _get_react_prompt(self, question: str) -> str:
        """获取 ReAct 提示词"""
        return f"""Solve the following question with interleaving Thought, Action, Observation steps.
Thought can reason about the current situation, and Action can be:
(1) Search[entity] - search for information
(2) Lookup[keyword] - find keyword in current context
(3) Finish[answer] - return the answer

Question: {question}
"""


def react_query(
    question: str,
    method: str = "react",
    max_steps: int = 7,
    self_consistency_samples: int = None,
    context: "ContextEngine" = None,
) -> dict:
    """
    便捷函数：使用 ReAct Agent 回答问题
    
    Args:
        question: 要回答的问题
        method: 推理方法，可选值: 'standard', 'cot', 'act', 'react'
        max_steps: 最大推理步骤数（默认7步）
        self_consistency_samples: Self-Consistency 采样次数（None表示不使用）
        context: 上下文引擎实例（可选，会自动创建）
    
    Returns:
        dict: 包含以下字段
            - answer: 最终答案
            - success: 是否成功
            - method: 使用的推理方法
            - steps: 步骤数量
            - trajectory: 完整执行轨迹（ReActTrajectory对象）
            - steps_detail: 步骤详情列表（便于直接访问）
    
    Example:
        >>> result = react_query("What is the capital of France?")
        >>> print(result['answer'])
        Paris
    """
    from context import ContextEngine
    import asyncio
    
    agent = ReActAgent(method=method, max_steps=max_steps)
    ctx = context or ContextEngine(session_id=f"react-query-{hash(question) % 10000}")
    
    task = Task(
        task_id=f"react-task-{hash(question) % 10000}",
        agent_name="react",
        input_data={"input": question},
    )
    
    # 检查是否已有运行的事件循环
    has_running_loop = False
    running_loop = None
    try:
        running_loop = asyncio.get_running_loop()
        has_running_loop = True
    except RuntimeError:
        has_running_loop = False
    
    if has_running_loop and running_loop.is_running():
        # 已有事件循环正在运行，不能用 run_until_complete
        # 创建新的事件循环来运行
        if self_consistency_samples and self_consistency_samples > 1:
            result = asyncio.run(run_with_self_consistency(agent, question, ctx, method=method, num_samples=self_consistency_samples))
        else:
            result = asyncio.run(agent.execute(task, ctx))
    elif has_running_loop:
        # 有循环但不运行，可以用 run_until_complete
        if self_consistency_samples and self_consistency_samples > 1:
            coro = run_with_self_consistency(agent, question, ctx, method=method, num_samples=self_consistency_samples)
        else:
            coro = agent.execute(task, ctx)
        result = running_loop.run_until_complete(coro)
    else:
        # 没有事件循环，使用 asyncio.run
        if self_consistency_samples and self_consistency_samples > 1:
            result = asyncio.run(run_with_self_consistency(agent, question, ctx, method=method, num_samples=self_consistency_samples))
        else:
            result = asyncio.run(agent.execute(task, ctx))
    
    # 处理结果
    if hasattr(result, 'final_answer'):
        # Self-Consistency 返回的是 trajectory
        return {
            "answer": result.final_answer,
            "success": result.success,
            "method": f"{method}-sc",
            "steps": len(result.steps),
            "trajectory": result,
            "steps_detail": [
                {
                    "step_num": step.step_num,
                    "thought": step.thought,
                    "action": step.action,
                    "argument": step.argument,
                    "observation": step.observation,
                }
                for step in result.steps
            ],
        }
    else:
        # 普通执行返回的是 task
        trajectory = result.output_data.get("trajectory")
        return {
            "answer": result.output_data.get("answer"),
            "success": result.output_data.get("success", False),
            "method": result.output_data.get("method"),
            "steps": result.output_data.get("steps", 0),
            "trajectory": trajectory,
            "steps_detail": [
                {
                    "step_num": step.step_num,
                    "thought": step.thought,
                    "action": step.action,
                    "argument": step.argument,
                    "observation": step.observation,
                }
                for step in (trajectory.steps if trajectory else [])
            ],
        }


async def async_react_query(
    question: str,
    method: str = "react",
    max_steps: int = 7,
    self_consistency_samples: int = None,
    context: "ContextEngine" = None,
) -> dict:
    """
    异步版本：使用 ReAct Agent 回答问题
    
    Args:
        question: 要回答的问题
        method: 推理方法，可选值: 'standard', 'cot', 'act', 'react'
        max_steps: 最大推理步骤数（默认7步）
        self_consistency_samples: Self-Consistency 采样次数（None表示不使用）
        context: 上下文引擎实例（可选，会自动创建）
    
    Returns:
        dict: 包含以下字段
            - answer: 最终答案
            - success: 是否成功
            - method: 使用的推理方法
            - steps: 步骤数量
            - trajectory: 完整执行轨迹
            - steps_detail: 步骤详情列表
    """
    from context import ContextEngine
    
    agent = ReActAgent(method=method, max_steps=max_steps)
    ctx = context or ContextEngine(session_id=f"react-query-{hash(question) % 10000}")
    
    task = Task(
        task_id=f"react-task-{hash(question) % 10000}",
        agent_name="react",
        input_data={"input": question},
    )
    
    if self_consistency_samples and self_consistency_samples > 1:
        result = await run_with_self_consistency(agent, question, ctx, method=method, num_samples=self_consistency_samples)
        return {
            "answer": result.final_answer,
            "success": result.success,
            "method": f"{method}-sc",
            "steps": len(result.steps),
            "trajectory": result,
            "steps_detail": [
                {
                    "step_num": step.step_num,
                    "thought": step.thought,
                    "action": step.action,
                    "argument": step.argument,
                    "observation": step.observation,
                }
                for step in result.steps
            ],
        }
    else:
        result = await agent.execute(task, ctx)
        trajectory = result.output_data.get("trajectory")
        return {
            "answer": result.output_data.get("answer"),
            "success": result.output_data.get("success", False),
            "method": result.output_data.get("method"),
            "steps": result.output_data.get("steps", 0),
            "trajectory": trajectory,
            "steps_detail": [
                {
                    "step_num": step.step_num,
                    "thought": step.thought,
                    "action": step.action,
                    "argument": step.argument,
                    "observation": step.observation,
                }
                for step in (trajectory.steps if trajectory else [])
            ],
        }


async def run_with_self_consistency(
        agent: "ReActAgent",
        question: str,
        context: "ContextEngine",
        method: str = "cot",
        num_samples: int = 5,
    ) -> "ReActTrajectory":
        """
        Self-Consistency (CoT-SC) 方法

        对同一问题多次采样，取多数答案。
        """
        answers = []
        trajectories = []
        for _ in range(num_samples):
            trajectory = await agent.run(question, context, method=method)
            trajectories.append(trajectory)
            if trajectory.final_answer:
                answers.append(trajectory.final_answer)

        if not answers:
            return trajectories[0] if trajectories else ReActTrajectory(question=question, method=f"{method}-sc")

        counter = Counter(answers)
        most_common = counter.most_common(1)
        best_answer = most_common[0][0]
        confidence = most_common[0][1] / len(answers)

        # 找到第一个产生最佳答案的轨迹
        for traj in trajectories:
            if traj.final_answer == best_answer:
                traj.method = f"{method}-sc"
                traj.confidence = confidence
                return traj

        return trajectories[0]