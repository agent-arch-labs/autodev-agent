from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(BaseModel):
    task_id: str
    agent_name: str
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    status: AgentStatus = AgentStatus.IDLE
    error: Optional[str] = None


class AgentContext(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    project_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    shared_memory: Dict[str, Any] = Field(default_factory=dict)


class BaseAgent(ABC):
    name: str
    description: str

    def __init__(self, model: str = "gpt-4", temperature: float = 0.7):
        self.model = model
        self.temperature = temperature
        self.status = AgentStatus.IDLE

    @abstractmethod
    async def execute(self, task: Task, context: "ContextEngine") -> Task:
        pass

    async def plan(self, task: Task, context: "ContextEngine") -> List[Dict[str, Any]]:
        return [{"action": "execute", "target": "self"}]

    def validate_input(self, task: Task) -> bool:
        return True


class CoordinatorAgent(BaseAgent):
    name = "coordinator"
    description = "Main coordinator for managing agent workflows"

    def __init__(self, agents: List[BaseAgent], **kwargs):
        super().__init__(**kwargs)
        self.agents = {agent.name: agent for agent in agents}

    async def execute(self, task: Task, context: "ContextEngine") -> Task:
        self.status = AgentStatus.RUNNING
        try:
            subtasks = await self.plan(task, context)
            results = []
            for subtask in subtasks:
                agent_name = subtask.get("agent")
                if agent_name in self.agents:
                    subtask_input = subtask.get("input", task.input_data)
                    subtask_model = Task(
                        task_id=f"{task.task_id}.{agent_name}",
                        agent_name=agent_name,
                        input_data=subtask_input,
                    )
                    agent = self.agents[agent_name]
                    result = await agent.execute(subtask_model, context)
                    results.append(result)
                    context.shared_memory.set(f"result.{agent_name}", result.output_data)

            task.output_data = {"subtasks": [r.model_dump() for r in results]}
            task.status = AgentStatus.COMPLETED
        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
        finally:
            self.status = AgentStatus.IDLE
        return task

    async def plan(self, task: Task, context: "ContextEngine") -> List[Dict[str, Any]]:
        return [
            {"agent": "requirement", "input": task.input_data},
            {"agent": "architect", "input": task.input_data},
            {"agent": "function", "input": task.input_data},
            {"agent": "coding", "input": task.input_data},
            {"agent": "test", "input": task.input_data},
        ]