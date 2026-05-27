from __future__ import annotations
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING
from pydantic import BaseModel, Field
from enum import Enum
import asyncio
import uuid

if TYPE_CHECKING:
    from context.engine import ContextEngine


class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStep(BaseModel):
    step_id: str
    name: str
    agent_name: str
    input_mapping: Dict[str, str] = Field(default_factory=dict)
    output_key: Optional[str] = None
    status: WorkflowStatus = WorkflowStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None


class Workflow(BaseModel):
    workflow_id: str
    name: str
    steps: List[WorkflowStep] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step: Optional[str] = None


class WorkflowEngine:
    def __init__(self):
        self.workflows: Dict[str, Workflow] = {}
        self._executors: Dict[str, Callable] = {}

    def register_executor(self, agent_name: str, executor: Callable) -> None:
        self._executors[agent_name] = executor

    def create_workflow(self, workflow_id: str, name: str, steps: List[Dict[str, Any]]) -> Workflow:
        workflow_steps = []
        for i, step_config in enumerate(steps):
            step = WorkflowStep(
                step_id=f"{workflow_id}.step.{i}",
                name=step_config["name"],
                agent_name=step_config["agent_name"],
                input_mapping=step_config.get("input_mapping", {}),
                output_key=step_config.get("output_key"),
            )
            workflow_steps.append(step)

        workflow = Workflow(workflow_id=workflow_id, name=name, steps=workflow_steps)
        self.workflows[workflow_id] = workflow
        return workflow

    async def execute_workflow(self, workflow_id: str, initial_input: Dict[str, Any]) -> Workflow:
        from context.engine import ContextEngine

        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        workflow.status = WorkflowStatus.RUNNING
        context_data = initial_input.copy()
        context = ContextEngine(session_id=f"wf-{workflow_id}")

        for key, value in context_data.items():
            context.set_task_context(key, value)

        for step in workflow.steps:
            workflow.current_step = step.step_id
            step.status = WorkflowStatus.RUNNING

            try:
                executor = self._executors.get(step.agent_name)
                if not executor:
                    raise ValueError(f"No executor registered for agent {step.agent_name}")

                step_input = {}
                for source_key, target_key in step.input_mapping.items():
                    step_input[target_key] = context_data.get(source_key)

                from agents.base import Task
                task = Task(
                    task_id=step.step_id,
                    agent_name=step.agent_name,
                    input_data=step_input,
                )

                result = await executor(task, context)

                if step.output_key:
                    context_data[step.output_key] = result.output_data

                step.result = result.output_data
                step.status = WorkflowStatus.COMPLETED

            except Exception as e:
                step.status = WorkflowStatus.FAILED
                step.error = str(e)
                workflow.status = WorkflowStatus.FAILED
                return workflow

        workflow.status = WorkflowStatus.COMPLETED
        return workflow

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        return self.workflows.get(workflow_id)

    def list_workflows(self) -> List[Workflow]:
        return list(self.workflows.values())


class DAGWorkflowEngine(WorkflowEngine):
    def __init__(self):
        super().__init__()
        self._dag: Dict[str, List[str]] = {}

    def set_dag(self, workflow_id: str, dag: Dict[str, List[str]]) -> None:
        self._dag[workflow_id] = dag

    async def execute_dag_workflow(self, workflow_id: str, initial_input: Dict[str, Any]) -> Workflow:
        from context.engine import ContextEngine
        from agents.base import Task

        workflow = self.workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        dag = self._dag.get(workflow_id, {})
        workflow.status = WorkflowStatus.RUNNING
        context_data = initial_input.copy()
        context = ContextEngine(session_id=f"wf-{workflow_id}")

        for key, value in context_data.items():
            context.set_task_context(key, value)

        completed = set()
        pending = set(dag.keys())

        while pending:
            ready = [node for node in pending if all(dep in completed for dep in dag.get(node, []))]

            if not ready:
                workflow.status = WorkflowStatus.FAILED
                for step in workflow.steps:
                    if step.step_id.split(".")[-2] in pending:
                        step.status = WorkflowStatus.FAILED
                        step.error = "DAG dependency not satisfied"
                return workflow

            tasks = []
            for node in ready:
                step = next((s for s in workflow.steps if s.name == node), None)
                if step:
                    tasks.append(self._execute_step(step, context_data, context))

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for node, result in zip(ready, results):
                pending.remove(node)
                completed.add(node)
                step = next((s for s in workflow.steps if s.name == node), None)
                if step and not isinstance(result, Exception):
                    if step.output_key:
                        context_data[step.output_key] = result.output_data if hasattr(result, 'output_data') else result

            for node, result in zip(ready, results):
                if isinstance(result, Exception):
                    workflow.status = WorkflowStatus.FAILED
                    step = next((s for s in workflow.steps if s.name == node), None)
                    if step:
                        step.status = WorkflowStatus.FAILED
                        step.error = str(result)
                    return workflow

        workflow.status = WorkflowStatus.COMPLETED
        return workflow

    async def _execute_step(self, step: WorkflowStep, context_data: Dict[str, Any], context: "ContextEngine") -> Any:
        from agents.base import Task

        step.status = WorkflowStatus.RUNNING
        try:
            executor = self._executors.get(step.agent_name)
            if not executor:
                raise ValueError(f"No executor registered for agent {step.agent_name}")

            step_input = {}
            for source_key, target_key in step.input_mapping.items():
                step_input[target_key] = context_data.get(source_key)

            task = Task(
                task_id=step.step_id,
                agent_name=step.agent_name,
                input_data=step_input,
            )

            result = await executor(task, context)
            step.result = result.output_data
            step.status = WorkflowStatus.COMPLETED
            return result
        except Exception as e:
            step.status = WorkflowStatus.FAILED
            step.error = str(e)
            raise