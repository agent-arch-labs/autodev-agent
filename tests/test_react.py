"""
Tests for ReAct Agent
"""
import pytest
from agents import ReActAgent, Task, AgentStatus
from context import ContextEngine


class TestReActAgent:
    """测试 ReAct Agent 功能"""

    @pytest.fixture
    def react_agent(self):
        return ReActAgent(max_steps=5)

    @pytest.fixture
    def context(self):
        return ContextEngine(session_id="test-react")

    @pytest.mark.asyncio
    async def test_react_standard(self, react_agent, context):
        """测试标准问答方法"""
        task = Task(
            task_id="react-standard-1",
            agent_name="react",
            input_data={"input": "What is 2+2?"},
        )

        result = await react_agent.execute(task, context)
        
        assert result.status == AgentStatus.COMPLETED
        assert "answer" in result.output_data

    @pytest.mark.asyncio
    async def test_react_cot(self, react_agent, context):
        """测试链式思考方法"""
        react_agent.method = "cot"
        
        task = Task(
            task_id="react-cot-1",
            agent_name="react",
            input_data={"input": "What is the capital of France?"},
        )

        result = await react_agent.execute(task, context)
        
        assert result.status == AgentStatus.COMPLETED
        assert "answer" in result.output_data
        assert result.output_data["method"] == "cot"

    @pytest.mark.asyncio
    async def test_react_act(self, react_agent, context):
        """测试仅动作方法"""
        react_agent.method = "act"
        
        task = Task(
            task_id="react-act-1",
            agent_name="react",
            input_data={"input": "Search for Milhouse"},
        )

        result = await react_agent.execute(task, context)
        
        assert result.status == AgentStatus.COMPLETED
        assert "steps" in result.output_data
        assert result.output_data["method"] == "act"

    @pytest.mark.asyncio
    async def test_react_react(self, react_agent, context):
        """测试 ReAct 核心方法"""
        react_agent.method = "react"
        
        task = Task(
            task_id="react-react-1",
            agent_name="react",
            input_data={"input": "What is the elevation of Colorado?"},
        )

        result = await react_agent.execute(task, context)
        
        assert result.status == AgentStatus.COMPLETED
        assert "steps" in result.output_data
        assert result.output_data["method"] == "react"
        assert result.output_data["success"] is True

    @pytest.mark.asyncio
    async def test_react_with_empty_input(self, react_agent, context):
        """测试空输入"""
        task = Task(
            task_id="react-empty-1",
            agent_name="react",
            input_data={"input": ""},
        )

        result = await react_agent.execute(task, context)
        
        assert result.status == AgentStatus.FAILED
        assert "error" in result.output_data

    def test_extract_action(self, react_agent):
        """测试动作提取"""
        text = "Thought 1: Search for info.\nAction 1: Search[Colorado]"
        action = react_agent._extract_action(text)
        
        assert action is not None
        assert action["action"] == "search"
        assert action["argument"] == "Colorado"

    def test_extract_thought(self, react_agent):
        """测试思考提取"""
        text = "Thought 1: I need to analyze this.\nAction 1: Search[test]"
        thought = react_agent._extract_thought(text)
        
        assert thought is not None
        assert "analyze" in thought

    @pytest.mark.asyncio
    async def test_react_self_consistency(self, react_agent, context):
        """测试 Self-Consistency 方法"""
        answer, confidence = await react_agent.run_with_self_consistency(
            "Test question", context, num_samples=3
        )
        
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0