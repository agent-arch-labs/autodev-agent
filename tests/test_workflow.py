import pytest
from workflow import (
    WorkflowEngine,
    DAGWorkflowEngine,
    Workflow,
    WorkflowStep,
    WorkflowStatus,
)
from agents import Task, AgentStatus


class MockExecutor:
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.call_count = 0

    async def __call__(self, task, context):
        self.call_count += 1
        if self.should_fail:
            raise ValueError("Executor failed")
        task.output_data = {"result": f"executed with {task.input_data}"}
        task.status = AgentStatus.COMPLETED
        return task


@pytest.fixture
def workflow_engine():
    return WorkflowEngine()


@pytest.fixture
def dag_engine():
    return DAGWorkflowEngine()


class TestWorkflowEngine:
    def test_create_workflow(self, workflow_engine):
        steps = [
            {"name": "step1", "agent_name": "agent1", "output_key": "result1"},
            {"name": "step2", "agent_name": "agent2", "input_mapping": {"data": "result1"}, "output_key": "result2"},
        ]

        workflow = workflow_engine.create_workflow(
            workflow_id="wf-1",
            name="Test Workflow",
            steps=steps,
        )

        assert workflow.workflow_id == "wf-1"
        assert workflow.name == "Test Workflow"
        assert len(workflow.steps) == 2
        assert workflow.status == WorkflowStatus.PENDING

    def test_get_workflow(self, workflow_engine):
        workflow_engine.create_workflow(
            workflow_id="wf-get",
            name="Get Test",
            steps=[{"name": "step1", "agent_name": "agent1"}],
        )

        retrieved = workflow_engine.get_workflow("wf-get")
        assert retrieved is not None
        assert retrieved.workflow_id == "wf-get"

    def test_get_nonexistent_workflow(self, workflow_engine):
        retrieved = workflow_engine.get_workflow("nonexistent")
        assert retrieved is None

    def test_list_workflows(self, workflow_engine):
        workflow_engine.create_workflow("wf-1", "Workflow 1", [])
        workflow_engine.create_workflow("wf-2", "Workflow 2", [])

        workflows = workflow_engine.list_workflows()
        assert len(workflows) == 2

    def test_register_executor(self, workflow_engine):
        executor = MockExecutor()
        workflow_engine.register_executor("test_agent", executor)

        assert "test_agent" in workflow_engine._executors

    @pytest.mark.asyncio
    async def test_execute_workflow(self, workflow_engine):
        executor = MockExecutor()
        workflow_engine.register_executor("agent1", executor)

        workflow = workflow_engine.create_workflow(
            workflow_id="wf-exec",
            name="Execute Test",
            steps=[
                {"name": "step1", "agent_name": "agent1", "output_key": "result"},
            ],
        )

        result = await workflow_engine.execute_workflow(
            "wf-exec",
            {"input": "test"},
        )

        assert result.status == WorkflowStatus.COMPLETED
        assert executor.call_count == 1

    @pytest.mark.asyncio
    async def test_execute_workflow_not_found(self, workflow_engine):
        with pytest.raises(ValueError, match="Workflow .* not found"):
            await workflow_engine.execute_workflow("nonexistent", {})


class TestDAGWorkflowEngine:
    def test_set_dag(self, dag_engine):
        dag = {
            "A": [],
            "B": ["A"],
            "C": ["A"],
            "D": ["B", "C"],
        }

        dag_engine.set_dag("wf-dag", dag)

        assert "wf-dag" in dag_engine._dag

    @pytest.mark.asyncio
    async def test_execute_dag_linear(self, dag_engine):
        executor = MockExecutor()
        dag_engine.register_executor("agent", executor)

        dag_engine.create_workflow(
            workflow_id="wf-dag-linear",
            name="Linear DAG",
            steps=[
                {"name": "A", "agent_name": "agent", "output_key": "out_a"},
                {"name": "B", "agent_name": "agent", "input_mapping": {"x": "out_a"}, "output_key": "out_b"},
            ],
        )
        dag_engine.set_dag("wf-dag-linear", {"A": [], "B": ["A"]})

        result = await dag_engine.execute_dag_workflow("wf-dag-linear", {"input": "test"})

        assert result.status == WorkflowStatus.COMPLETED
        assert executor.call_count == 2

    @pytest.mark.asyncio
    async def test_execute_dag_parallel(self, dag_engine):
        executor = MockExecutor()
        dag_engine.register_executor("agent", executor)

        dag_engine.create_workflow(
            workflow_id="wf-dag-parallel",
            name="Parallel DAG",
            steps=[
                {"name": "A", "agent_name": "agent", "output_key": "out_a"},
                {"name": "B", "agent_name": "agent", "output_key": "out_b"},
                {"name": "C", "agent_name": "agent", "input_mapping": {"x": "out_a", "y": "out_b"}, "output_key": "out_c"},
            ],
        )
        dag_engine.set_dag("wf-dag-parallel", {"A": [], "B": [], "C": ["A", "B"]})

        result = await dag_engine.execute_dag_workflow("wf-dag-parallel", {})

        assert result.status == WorkflowStatus.COMPLETED
        assert executor.call_count == 3

    @pytest.mark.asyncio
    async def test_execute_dag_failure(self, dag_engine):
        executor = MockExecutor(should_fail=True)
        dag_engine.register_executor("agent", executor)

        dag_engine.create_workflow(
            workflow_id="wf-dag-fail",
            name="Failure DAG",
            steps=[
                {"name": "A", "agent_name": "agent"},
            ],
        )
        dag_engine.set_dag("wf-dag-fail", {"A": []})

        result = await dag_engine.execute_dag_workflow("wf-dag-fail", {})

        assert result.status == WorkflowStatus.FAILED


class TestWorkflowStep:
    def test_step_creation(self):
        step = WorkflowStep(
            step_id="step-1",
            name="Test Step",
            agent_name="test_agent",
        )

        assert step.step_id == "step-1"
        assert step.name == "Test Step"
        assert step.agent_name == "test_agent"
        assert step.status == WorkflowStatus.PENDING

    def test_step_with_mapping(self):
        step = WorkflowStep(
            step_id="step-2",
            name="Mapped Step",
            agent_name="test_agent",
            input_mapping={"source": "target", "data": "input"},
            output_key="result",
        )

        assert step.input_mapping == {"source": "target", "data": "input"}
        assert step.output_key == "result"

    def test_step_with_result(self):
        step = WorkflowStep(
            step_id="step-3",
            name="Result Step",
            agent_name="test_agent",
            status=WorkflowStatus.COMPLETED,
            result={"output": "data"},
        )

        assert step.status == WorkflowStatus.COMPLETED
        assert step.result == {"output": "data"}


class TestWorkflow:
    def test_workflow_creation(self):
        steps = [
            WorkflowStep(step_id="s1", name="Step 1", agent_name="agent1"),
            WorkflowStep(step_id="s2", name="Step 2", agent_name="agent2"),
        ]

        workflow = Workflow(
            workflow_id="wf-1",
            name="Test Workflow",
            steps=steps,
        )

        assert workflow.workflow_id == "wf-1"
        assert workflow.name == "Test Workflow"
        assert len(workflow.steps) == 2
        assert workflow.status == WorkflowStatus.PENDING
        assert workflow.current_step is None

    def test_workflow_with_current_step(self):
        workflow = Workflow(
            workflow_id="wf-2",
            name="Running Workflow",
            steps=[WorkflowStep(step_id="s1", name="Step 1", agent_name="agent1")],
            status=WorkflowStatus.RUNNING,
            current_step="s1",
        )

        assert workflow.status == WorkflowStatus.RUNNING
        assert workflow.current_step == "s1"