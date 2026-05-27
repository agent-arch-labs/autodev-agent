from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import uuid
import asyncio

from agents import Task, get_agent_factory
from context import ContextManager
from workflow import DAGWorkflowEngine


app = FastAPI(title="AutoDev Gateway", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


agent_factory = get_agent_factory()
workflow_engine = DAGWorkflowEngine()


def _resolve_user_id(request_user_id: Optional[str], session_id: str) -> str:
    """解析 user_id: 优先使用请求中的 user_id, 否则回退到 session_id"""
    return request_user_id or session_id


async def _build_agent_map(user_id: str) -> Dict[str, Any]:
    """为指定用户构建 Agent 映射（并行获取所有 Agent，减少延迟）"""
    agent_map = await agent_factory.batch_get_agents(user_id)
    coordinator = await agent_factory.get_coordinator(user_id)
    agent_map["coordinator"] = coordinator
    return agent_map


async def _build_executors_for_workflow(user_id: str) -> Dict[str, Any]:
    """为指定用户构建工作流执行器映射（并行获取）"""
    agents = await agent_factory.batch_get_agents(user_id)
    return {name: agent.execute for name, agent in agents.items()}


class ExecuteRequest(BaseModel):
    input: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    workflow: Optional[str] = None


class WorkflowCreateRequest(BaseModel):
    name: str
    steps: List[Dict[str, Any]]
    user_id: Optional[str] = None


class WorkflowExecuteRequest(BaseModel):
    workflow_id: str
    input_data: Dict[str, Any]
    user_id: Optional[str] = None


class AgentExecuteRequest(BaseModel):
    agent_name: str
    input_data: Dict[str, Any]
    session_id: Optional[str] = None
    user_id: Optional[str] = None


connections: Dict[str, WebSocket] = {}


@app.get("/")
def root():
    return {
        "service": "AutoDev Gateway",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "autodev-gateway"}


@app.post("/api/v1/execute")
async def execute(request: ExecuteRequest):
    session_id = request.session_id or str(uuid.uuid4())
    user_id = _resolve_user_id(request.user_id, session_id)
    context = ContextManager.get_context(session_id)

    executors = await _build_executors_for_workflow(user_id)
    for agent_name, executor in executors.items():
        workflow_engine.register_executor(agent_name, executor)

    workflow = workflow_engine.create_workflow(
        workflow_id=f"wf-{session_id}",
        name="Multi-Agent SDLC Workflow",
        steps=[
            {"name": "requirement", "agent_name": "requirement", "input_mapping": {"input": "input"}, "output_key": "prd"},
            {"name": "architect", "agent_name": "architect", "input_mapping": {"input": "input", "prd": "prd"}, "output_key": "architecture"},
            {"name": "function", "agent_name": "function", "input_mapping": {"prd": "prd", "architecture": "architecture"}, "output_key": "tasks"},
            {"name": "coding", "agent_name": "coding", "input_mapping": {"tasks": "tasks", "architecture": "architecture"}, "output_key": "code_files"},
            {"name": "test", "agent_name": "test", "input_mapping": {"code_files": "code_files", "tasks": "tasks"}},
        ],
    )

    result = await workflow_engine.execute_dag_workflow(
        workflow.workflow_id,
        {"input": request.input}
    )

    output = {
        "session_id": session_id,
        "user_id": user_id,
        "workflow_id": workflow.workflow_id,
        "workflow_status": result.status.value,
        "steps_completed": sum(1 for s in result.steps if s.status == "completed"),
        "total_steps": len(result.steps),
        "results": {},
    }

    for step in result.steps:
        if step.result and isinstance(step.result, dict):
            output["results"][step.name] = step.result

    return output


@app.post("/api/v1/agent/execute")
async def execute_agent(request: AgentExecuteRequest):
    session_id = request.session_id or str(uuid.uuid4())
    user_id = _resolve_user_id(request.user_id, session_id)
    context = ContextManager.get_context(session_id)

    agent_map = await _build_agent_map(user_id)

    agent = agent_map.get(request.agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {request.agent_name} not found")

    task = Task(
        task_id=f"task-{uuid.uuid4()}",
        agent_name=request.agent_name,
        input_data=request.input_data,
    )

    result = await agent.execute(task, context)

    return {
        "task_id": result.task_id,
        "agent_name": result.agent_name,
        "status": result.status.value,
        "output_data": result.output_data,
        "error": result.error,
        "session_id": session_id,
        "user_id": user_id,
    }


@app.post("/api/v1/workflow/create")
async def create_workflow(request: WorkflowCreateRequest):
    workflow_id = f"wf-{uuid.uuid4()}"
    workflow = workflow_engine.create_workflow(
        workflow_id=workflow_id,
        name=request.name,
        steps=request.steps,
    )

    return {
        "workflow_id": workflow.workflow_id,
        "name": workflow.name,
        "status": workflow.status.value,
        "steps": [{"step_id": s.step_id, "name": s.name, "agent_name": s.agent_name} for s in workflow.steps],
    }


@app.post("/api/v1/workflow/execute")
async def execute_workflow(request: WorkflowExecuteRequest):
    user_id = request.user_id or request.workflow_id
    executors = await _build_executors_for_workflow(user_id)
    for agent_name, executor in executors.items():
        workflow_engine.register_executor(agent_name, executor)

    result = await workflow_engine.execute_dag_workflow(
        request.workflow_id,
        request.input_data,
    )

    return {
        "workflow_id": result.workflow_id,
        "user_id": user_id,
        "status": result.status.value,
        "current_step": result.current_step,
        "steps": [
            {
                "step_id": s.step_id,
                "name": s.name,
                "status": s.status.value,
                "result": s.result,
                "error": s.error,
            }
            for s in result.steps
        ],
    }


@app.get("/api/v1/workflow/{workflow_id}")
async def get_workflow(workflow_id: str):
    workflow = workflow_engine.get_workflow(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "workflow_id": workflow.workflow_id,
        "name": workflow.name,
        "status": workflow.status.value,
        "current_step": workflow.current_step,
        "steps": [
            {
                "step_id": s.step_id,
                "name": s.name,
                "status": s.status.value,
            }
            for s in workflow.steps
        ],
    }


@app.get("/api/v1/sessions")
async def list_sessions():
    sessions = ContextManager.list_sessions()
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/v1/session/{session_id}")
async def get_session(session_id: str):
    context = ContextManager.get_context(session_id)
    return {
        "session_id": context.session_id,
        "task_context": context.task_context,
        "code_context": context.code_context,
        "project_context": context.project_context,
        "conversation_history": context.conversation_history,
    }


@app.delete("/api/v1/session/{session_id}")
async def delete_session(session_id: str):
    await agent_factory.remove_user(session_id)
    ContextManager.delete_context(session_id)
    return {"message": f"Session {session_id} deleted", "session_id": session_id}


@app.get("/api/v1/agents")
async def list_agents():
    agent_descriptions = {
        "requirement": "Analyzes user requirements and generates PRD documents",
        "architect": "Designs technical architecture for software systems",
        "function": "Decomposes requirements into development tasks",
        "coding": "Generates and manages code files",
        "test": "Generates test suites and validates code quality",
        "runtime": "Handles deployment and runtime configuration",
        "coordinator": "Main coordinator for managing agent workflows",
    }
    return {
        "agents": [
            {"name": name, "description": desc}
            for name, desc in agent_descriptions.items()
        ],
        "active_users": agent_factory.get_user_count(),
    }


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    connections[session_id] = websocket
    user_id = _resolve_user_id(None, session_id)

    try:
        while True:
            data = await websocket.receive_json()
            agent_name = data.get("agent_name", "coordinator")
            input_data = data.get("input_data", {})
            ws_user_id = data.get("user_id", user_id)

            agent_map = await _build_agent_map(ws_user_id)

            agent = agent_map.get(agent_name)
            if not agent:
                await websocket.send_json({"error": f"Agent {agent_name} not found"})
                continue

            context = ContextManager.get_context(session_id)
            task = Task(
                task_id=f"task-{uuid.uuid4()}",
                agent_name=agent_name,
                input_data=input_data,
            )

            result = await agent.execute(task, context)

            await websocket.send_json({
                "task_id": result.task_id,
                "agent_name": result.agent_name,
                "status": result.status.value,
                "output_data": result.output_data,
                "error": result.error,
                "user_id": ws_user_id,
            })

    except WebSocketDisconnect:
        connections.pop(session_id, None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("gateway.main:app", host="0.0.0.0", port=8000, reload=True)