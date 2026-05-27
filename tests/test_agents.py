import pytest
from agents import (
    Task,
    AgentStatus,
    RequirementAgent,
    ArchitectAgent,
    FunctionAgent,
    CodingAgent,
    TestAgent,
    RuntimeAgent,
    CoordinatorAgent,
)
from context import ContextEngine


@pytest.fixture
def session_id():
    return "test-session-123"


@pytest.fixture
def agent_context(session_id):
    return ContextEngine(session_id=session_id)


@pytest.fixture
def sample_task():
    return Task(
        task_id="test-task-1",
        agent_name="test",
        input_data={"input": "我想做一个 AI 知识库系统"},
    )


class TestRequirementAgent:
    @pytest.mark.asyncio
    async def test_generate_prd(self, agent_context, sample_task):
        agent = RequirementAgent()
        result = await agent.execute(sample_task, agent_context)

        assert result.status == AgentStatus.COMPLETED
        assert result.output_data is not None
        assert "prd" in result.output_data
        assert "user_goals" in result.output_data
        assert "core_features" in result.output_data

    @pytest.mark.asyncio
    async def test_prd_structure(self, agent_context):
        agent = RequirementAgent()
        task = Task(
            task_id="test-task-2",
            agent_name="requirement",
            input_data={"input": "RAG 知识库搜索系统"},
        )
        result = await agent.execute(task, agent_context)

        prd = result.output_data["prd"]
        assert "title" in prd
        assert "user_goals" in prd
        assert "core_features" in prd
        assert "mvp" in prd
        assert "user_scenarios" in prd
        assert "risks" in prd
        assert "acceptance_criteria" in prd

    @pytest.mark.asyncio
    async def test_empty_input_fails(self, agent_context):
        agent = RequirementAgent()
        task = Task(
            task_id="test-task-3",
            agent_name="requirement",
            input_data={},
        )
        result = await agent.execute(task, agent_context)

        assert result.status == AgentStatus.FAILED
        assert result.error is not None


class TestArchitectAgent:
    @pytest.mark.asyncio
    async def test_design_architecture(self, agent_context):
        agent = ArchitectAgent()
        task = Task(
            task_id="test-arch-1",
            agent_name="architect",
            input_data={
                "input": "知识库系统",
                "prd": {"core_features": ["search", "upload", "download"]},
            },
        )
        result = await agent.execute(task, agent_context)

        assert result.status == AgentStatus.COMPLETED
        assert "architecture" in result.output_data

        arch = result.output_data["architecture"]
        assert "tech_stack" in arch
        assert "modules" in arch
        assert "data_flow" in arch

    @pytest.mark.asyncio
    async def test_tech_stack_selection(self, agent_context):
        agent = ArchitectAgent()
        task = Task(
            task_id="test-arch-2",
            agent_name="architect",
            input_data={
                "input": "web application",
                "prd": {},
            },
        )
        result = await agent.execute(task, agent_context)

        tech_stack = result.output_data["tech_stack"]
        assert len(tech_stack) > 0
        layers = [t["layer"] for t in tech_stack]
        assert "frontend" in layers
        assert "backend" in layers


class TestFunctionAgent:
    @pytest.mark.asyncio
    async def test_decompose_tasks(self, agent_context):
        agent = FunctionAgent()
        task = Task(
            task_id="test-func-1",
            agent_name="function",
            input_data={
                "prd": {"core_features": ["search", "upload"]},
                "architecture": {
                    "modules": [
                        {"module_id": "mod-1", "name": "Auth", "description": "User authentication", "dependencies": []},
                        {"module_id": "mod-2", "name": "Search", "description": "Search functionality", "dependencies": ["mod-1"]},
                    ]
                },
            },
        )
        result = await agent.execute(task, agent_context)

        assert result.status == AgentStatus.COMPLETED
        assert "tasks" in result.output_data
        assert result.output_data["task_count"] > 0

    @pytest.mark.asyncio
    async def test_task_priorities(self, agent_context):
        agent = FunctionAgent()
        task = Task(
            task_id="test-func-2",
            agent_name="function",
            input_data={
                "prd": {"core_features": ["feature1", "feature2", "feature3"]},
                "architecture": {"modules": []},
            },
        )
        result = await agent.execute(task, agent_context)

        priorities = result.output_data["priorities"]
        assert "P0" in priorities
        assert "P1" in priorities


class TestCodingAgent:
    @pytest.mark.asyncio
    async def test_generate_code(self, agent_context):
        agent = CodingAgent()
        task = Task(
            task_id="test-code-1",
            agent_name="coding",
            input_data={
                "tasks": [
                    {"task_id": "task-1", "title": "Implement auth"},
                    {"task_id": "task-2", "title": "Implement search"},
                ],
                "architecture": {
                    "tech_stack": [
                        {"layer": "backend", "technology": "FastAPI"},
                        {"layer": "database", "technology": "PostgreSQL"},
                    ]
                },
            },
        )
        result = await agent.execute(task, agent_context)

        assert result.status == AgentStatus.COMPLETED
        assert "code_files" in result.output_data
        assert result.output_data["file_count"] > 0

    @pytest.mark.asyncio
    async def test_code_files_structure(self, agent_context):
        agent = CodingAgent()
        task = Task(
            task_id="test-code-2",
            agent_name="coding",
            input_data={
                "tasks": [{"task_id": "task-1", "title": "Test"}],
                "architecture": {"tech_stack": [{"layer": "backend", "technology": "FastAPI"}]},
            },
        )
        result = await agent.execute(task, agent_context)

        code_files = result.output_data["code_files"]
        assert len(code_files) > 0

        main_py = next((f for f in code_files if f["file_path"] == "main.py"), None)
        assert main_py is not None
        assert "content" in main_py
        assert "fastapi" in main_py["content"].lower()


class TestTestAgent:
    @pytest.mark.asyncio
    async def test_generate_tests(self, agent_context):
        agent = TestAgent()
        task = Task(
            task_id="test-test-1",
            agent_name="test",
            input_data={
                "code_files": [
                    {"file_path": "main.py", "language": "python"},
                    {"file_path": "api/routes.py", "language": "python"},
                ],
                "tasks": [{"task_id": "task-1", "title": "Test"}],
            },
        )
        result = await agent.execute(task, agent_context)

        assert result.status == AgentStatus.COMPLETED
        assert "test_results" in result.output_data
        assert result.output_data["tests_passed"] >= 0


class TestRuntimeAgent:
    @pytest.mark.asyncio
    async def test_prepare_deployment(self, agent_context):
        agent = RuntimeAgent()
        task = Task(
            task_id="test-runtime-1",
            agent_name="runtime",
            input_data={
                "code_files": [{"file_path": "main.py", "language": "python"}],
            },
        )
        result = await agent.execute(task, agent_context)

        assert result.status == AgentStatus.COMPLETED
        assert "deployment" in result.output_data
        assert "dockerfile" in result.output_data["deployment"]
        assert "docker_compose" in result.output_data["deployment"]

    @pytest.mark.asyncio
    async def test_dockerfile_generation(self, agent_context):
        agent = RuntimeAgent()
        task = Task(
            task_id="test-runtime-2",
            agent_name="runtime",
            input_data={"code_files": []},
        )
        result = await agent.execute(task, agent_context)

        dockerfile = result.output_data["deployment"]["dockerfile"]
        assert "FROM python" in dockerfile
        assert "EXPOSE" in dockerfile
        assert "CMD" in dockerfile


class TestCoordinatorAgent:
    @pytest.mark.asyncio
    async def test_coordinator_planning(self, agent_context, sample_task):
        requirement = RequirementAgent()
        architect = ArchitectAgent()

        coordinator = CoordinatorAgent(agents=[requirement, architect])
        plan = await coordinator.plan(sample_task, agent_context)

        assert len(plan) > 0
        agent_names = [p.get("agent") for p in plan]
        assert "requirement" in agent_names

    @pytest.mark.asyncio
    async def test_coordinator_execution(self, agent_context):
        requirement = RequirementAgent()
        architect = ArchitectAgent()

        coordinator = CoordinatorAgent(agents=[requirement, architect])

        task = Task(
            task_id="test-coord-1",
            agent_name="coordinator",
            input_data={"input": "AI 知识库系统"},
        )

        result = await coordinator.execute(task, agent_context)

        assert result.status in [AgentStatus.COMPLETED, AgentStatus.FAILED]


class TestAgentContext:
    def test_task_context_operations(self):
        context = ContextEngine(session_id="test-session")

        context.set_task_context("key1", "value1")
        assert context.get_task_context("key1") == "value1"

        context.set_task_context("key2", {"nested": "value"})
        assert context.get_task_context("key2") == {"nested": "value"}

    def test_code_context_operations(self):
        context = ContextEngine(session_id="test-session")

        context.set_code_context("code_key", "code_value")
        assert context.get_code_context("code_key") == "code_value"

    def test_project_context_operations(self):
        context = ContextEngine(session_id="test-session")

        context.set_project_context("project_key", "project_value")
        assert context.get_project_context("project_key") == "project_value"

    def test_conversation_history(self):
        context = ContextEngine(session_id="test-session")

        context.add_conversation("user", "Hello")
        context.add_conversation("assistant", "Hi there")

        history = context.get_conversation_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"

    def test_conversation_history_limit(self):
        context = ContextEngine(session_id="test-session")

        for i in range(5):
            context.add_conversation("user", f"Message {i}")

        history = context.get_conversation_history(limit=3)
        assert len(history) == 3


class TestTask:
    def test_task_creation(self):
        task = Task(
            task_id="test-1",
            agent_name="test",
            input_data={"key": "value"},
        )

        assert task.task_id == "test-1"
        assert task.agent_name == "test"
        assert task.input_data == {"key": "value"}
        assert task.status == AgentStatus.IDLE
        assert task.output_data is None
        assert task.error is None

    def test_task_with_output(self):
        task = Task(
            task_id="test-2",
            agent_name="test",
            input_data={},
            output_data={"result": "success"},
            status=AgentStatus.COMPLETED,
        )

        assert task.output_data == {"result": "success"}
        assert task.status == AgentStatus.COMPLETED

    def test_task_with_error(self):
        task = Task(
            task_id="test-3",
            agent_name="test",
            input_data={},
            status=AgentStatus.FAILED,
            error="Something went wrong",
        )

        assert task.status == AgentStatus.FAILED
        assert task.error == "Something went wrong"