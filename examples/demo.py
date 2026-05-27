import asyncio
from agents import (
    CoordinatorAgent,
    RequirementAgent,
    ArchitectAgent,
    FunctionAgent,
    CodingAgent,
    TestAgent,
    RuntimeAgent,
    ReActAgent,
    Task,
)
from context import ContextEngine
from workflow import DAGWorkflowEngine


async def run_single_agent_demo():
    print("=" * 60)
    print("Demo 1: Single Agent Execution")
    print("=" * 60)

    agent = RequirementAgent()
    context = ContextEngine(session_id="demo-single")

    task = Task(
        task_id="task-1",
        agent_name="requirement",
        input_data={"input": "我想做一个 Obsidian + RAG 的 AI 知识库"},
    )

    result = await agent.execute(task, context)

    print(f"\nTask Status: {result.status.value}")
    print(f"\nGenerated PRD:")
    print(f"  Title: {result.output_data['prd']['title']}")
    print(f"  User Goals: {len(result.output_data['prd']['user_goals'])} items")
    print(f"  Core Features: {len(result.output_data['prd']['core_features'])} items")
    print(f"  MVP Items: {len(result.output_data['prd']['mvp'])} items")
    print(f"  Risks: {len(result.output_data['prd']['risks'])} items")


async def run_multi_agent_demo():
    print("\n" + "=" * 60)
    print("Demo 2: Multi-Agent Pipeline")
    print("=" * 60)

    requirement_agent = RequirementAgent()
    architect_agent = ArchitectAgent()
    function_agent = FunctionAgent()
    coding_agent = CodingAgent()
    test_agent = TestAgent()
    runtime_agent = RuntimeAgent()

    coordinator = CoordinatorAgent(
        agents=[
            requirement_agent,
            architect_agent,
            function_agent,
            coding_agent,
            test_agent,
            runtime_agent,
        ]
    )

    context = ContextEngine(session_id="demo-multi")

    task = Task(
        task_id="task-multi-1",
        agent_name="coordinator",
        input_data={"input": "RAG 知识库搜索系统"},
    )

    result = await coordinator.execute(task, context)

    print(f"\nPipeline Status: {result.status.value}")
    if result.output_data:
        subtasks = result.output_data.get("subtasks", [])
        print(f"\nCompleted {len(subtasks)} subtasks:")
        for st in subtasks:
            print(f"  - {st['agent_name']}: {st['status']}")


async def run_workflow_demo():
    print("\n" + "=" * 60)
    print("Demo 3: DAG Workflow Engine")
    print("=" * 60)

    requirement_agent = RequirementAgent()
    architect_agent = ArchitectAgent()
    function_agent = FunctionAgent()

    workflow_engine = DAGWorkflowEngine()

    workflow_engine.register_executor("requirement", requirement_agent.execute)
    workflow_engine.register_executor("architect", architect_agent.execute)
    workflow_engine.register_executor("function", function_agent.execute)

    workflow = workflow_engine.create_workflow(
        workflow_id="wf-demo",
        name="Knowledge Base Pipeline",
        steps=[
            {
                "name": "requirement",
                "agent_name": "requirement",
                "input_mapping": {"input": "input"},
                "output_key": "prd",
            },
            {
                "name": "architect",
                "agent_name": "architect",
                "input_mapping": {"input": "input", "prd": "prd"},
                "output_key": "architecture",
            },
            {
                "name": "function",
                "agent_name": "function",
                "input_mapping": {"prd": "prd", "architecture": "architecture"},
                "output_key": "tasks",
            },
        ],
    )

    workflow_engine.set_dag("wf-demo", {
        "requirement": [],
        "architect": ["requirement"],
        "function": ["architect"],
    })

    result = await workflow_engine.execute_dag_workflow(
        "wf-demo",
        {"input": "AI-powered document search system"},
    )

    print(f"\nWorkflow Status: {result.status.value}")
    print(f"Steps Completed: {sum(1 for s in result.steps if s.status.value == 'completed')}/{len(result.steps)}")

    for step in result.steps:
        print(f"\n  Step: {step.name}")
        print(f"    Status: {step.status.value}")
        if step.result and isinstance(step.result, dict):
            if "prd" in step.result:
                print(f"    PRD Generated: {len(step.result['prd'].get('core_features', []))} features")
            if "architecture" in step.result:
                print(f"    Architecture: {step.result['architecture'].get('architecture_type', 'N/A')}")
            if "tasks" in step.result:
                tasks_result = step.result["tasks"]
                if isinstance(tasks_result, dict):
                    print(f"    Tasks: {tasks_result.get('task_count', 0)} tasks")
                elif isinstance(tasks_result, list):
                    print(f"    Tasks: {len(tasks_result)} items")


async def run_architect_demo():
    print("\n" + "=" * 60)
    print("Demo 4: Architect Agent Detail")
    print("=" * 60)

    agent = ArchitectAgent()
    context = ContextEngine(session_id="demo-arch")

    task = Task(
        task_id="task-arch-1",
        agent_name="architect",
        input_data={
            "input": "企业级知识管理系统",
            "prd": {"core_features": ["文档上传", "全文搜索", "权限管理", "数据分析"]},
        },
    )

    result = await agent.execute(task, context)

    print(f"\nArchitect Status: {result.status.value}")

    arch = result.output_data["architecture"]
    print(f"\nArchitecture Type: {arch['architecture_type']}")

    print("\nTech Stack:")
    for tech in arch["tech_stack"]:
        print(f"  - {tech['layer']}: {tech['technology']}")

    print(f"\nModules: {len(arch['modules'])}")
    for mod in arch["modules"][:3]:
        print(f"  - {mod['name']}: {mod['description'][:40]}...")

    print(f"\nAPI Endpoints: {len(arch['api_spec']['endpoints'])}")


async def run_coding_demo():
    print("\n" + "=" * 60)
    print("Demo 5: Coding Agent - Code Generation")
    print("=" * 60)

    agent = CodingAgent()
    context = ContextEngine(session_id="demo-code")

    task = Task(
        task_id="task-code-1",
        agent_name="coding",
        input_data={
            "tasks": [
                {"task_id": "task-1", "title": "User authentication", "priority": "P0"},
                {"task_id": "task-2", "title": "Document upload", "priority": "P1"},
                {"task_id": "task-3", "title": "Search functionality", "priority": "P1"},
            ],
            "architecture": {
                "tech_stack": [
                    {"layer": "backend", "technology": "FastAPI"},
                    {"layer": "database", "technology": "PostgreSQL"},
                    {"layer": "cache", "technology": "Redis"},
                ]
            },
        },
    )

    result = await agent.execute(task, context)

    print(f"\nCoding Status: {result.status.value}")
    print(f"\nGenerated {result.output_data['file_count']} files:")

    summary = result.output_data["summary"]
    print(f"  Languages: {summary['languages']}")
    print(f"  Frameworks: {summary['frameworks']}")

    print("\nGenerated Files:")
    for file in result.output_data["code_files"]:
        print(f"  - {file['file_path']} ({file['language']})")


async def run_react_demo():
    print("\n" + "=" * 60)
    print("Demo 6: ReAct Agent - Reasoning & Action")
    print("=" * 60)

    agent = ReActAgent(method="react", max_steps=5)
    context = ContextEngine(session_id="demo-react")

    task = Task(
        task_id="task-react-1",
        agent_name="react",
        input_data={"input": "What is the elevation of Colorado orogeny's eastern sector?"},
    )

    result = await agent.execute(task, context)

    print(f"\nReAct Status: {result.status.value}")
    print(f"Method: {result.output_data['method']}")
    print(f"Success: {result.output_data['success']}")
    print(f"Steps: {result.output_data['steps']}")
    print(f"Answer: {result.output_data['answer']}")

    print("\nExecution Trajectory:")
    trajectory = result.output_data["trajectory"]
    for step in trajectory.steps:
        print(f"  Step {step.step_num}:")
        if step.thought:
            print(f"    Thought: {step.thought}")
        if step.action:
            print(f"    Action: {step.action}[{step.argument}]")
        if step.observation:
            print(f"    Observation: {step.observation}")


async def main():
    print("\n" + "=" * 60)
    print("AutoDev Core - Multi-Agent SDLC Platform Demo")
    print("=" * 60)

    await run_single_agent_demo()
    await run_multi_agent_demo()
    await run_workflow_demo()
    await run_architect_demo()
    await run_coding_demo()
    await run_react_demo()

    print("\n" + "=" * 60)
    print("All demos completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())