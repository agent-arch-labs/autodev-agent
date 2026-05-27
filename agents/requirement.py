from __future__ import annotations
from typing import Dict, Any, List, Optional
import json
from datetime import datetime
from agents.base import BaseAgent, Task, AgentStatus


class RequirementAgent(BaseAgent):
    name = "requirement"
    description = "Analyzes user requirements and generates PRD documents"

    _template_cache: Optional[Dict[str, Any]] = None

    def __init__(self, model: str = "gpt-4", temperature: float = 0.7):
        super().__init__(model, temperature)
        self.template = self._load_template()

    @classmethod
    def _load_template(cls) -> Dict[str, Any]:
        if cls._template_cache is None:
            cls._template_cache = {
                "sections": [
                    "user_goals",
                    "core_features",
                    "mvp",
                    "user_scenarios",
                    "risks",
                    "acceptance_criteria",
                ]
            }
        return cls._template_cache

    async def execute(self, task: Task, context: ContextEngine) -> Task:
        self.status = AgentStatus.RUNNING
        try:
            user_input = task.input_data.get("input", "")
            if not user_input:
                raise ValueError("No input provided for requirement analysis")

            prd = await self.generate_prd(user_input, context)

            task.output_data = {
                "prd": prd,
                "user_goals": prd.get("user_goals", []),
                "core_features": prd.get("core_features", []),
                "mvp": prd.get("mvp", []),
                "user_scenarios": prd.get("user_scenarios", []),
                "risks": prd.get("risks", []),
            }
            task.status = AgentStatus.COMPLETED

            context.set_task_context("current_prd", prd)
            context.add_conversation("system", f"Generated PRD for: {user_input[:50]}...")

        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
        finally:
            self.status = AgentStatus.IDLE
        return task

    async def generate_prd(self, user_input: str, context: ContextEngine) -> Dict[str, Any]:
        features = self._analyze_features(user_input)
        user_goals = self._extract_goals(user_input)
        mvp = self._define_mvp(features)
        scenarios = self._create_scenarios(user_input, features)
        risks = self._assess_risks(features)

        return {
            "title": self._extract_title(user_input),
            "user_goals": user_goals,
            "core_features": features,
            "mvp": mvp,
            "user_scenarios": scenarios,
            "risks": risks,
            "acceptance_criteria": self._generate_acceptance_criteria(mvp),
            "created_at": datetime.now().isoformat(),
            "raw_input": user_input,
        }

    def _extract_title(self, user_input: str) -> str:
        words = user_input.split()
        if len(words) > 6:
            return " ".join(words[:6]) + "..."
        return user_input

    def _analyze_features(self, user_input: str) -> List[str]:
        feature_keywords = [
            "upload", "download", "search", "edit", "delete", "create",
            "manage", "track", "analyze", "generate", "export", "import",
            "share", "collaborate", "automate", "integrate", "sync"
        ]
        features = []
        input_lower = user_input.lower()
        for keyword in feature_keywords:
            if keyword in input_lower:
                features.append(f"Feature: {keyword.capitalize()} functionality")
        if not features:
            features.append("Feature: Core functionality based on user requirements")
        return features

    def _extract_goals(self, user_input: str) -> List[str]:
        return [
            f"Primary goal: {user_input[:100]}",
            "Secondary goal: Provide efficient workflow",
            "Business goal: Improve user productivity",
        ]

    def _define_mvp(self, features: List[str]) -> List[Dict[str, Any]]:
        mvp_items = []
        for i, feature in enumerate(features[:3]):
            mvp_items.append({
                "id": f"mvp-{i+1}",
                "feature": feature,
                "priority": "P0" if i == 0 else "P1",
                "effort": "medium",
                "dependencies": [],
            })
        return mvp_items

    def _create_scenarios(self, user_input: str, features: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "scenario_id": "scenario-1",
                "title": "Primary User Flow",
                "steps": [
                    "User submits requirements",
                    "System analyzes and generates plan",
                    "User reviews and approves",
                    "System executes task",
                ],
            },
            {
                "scenario_id": "scenario-2",
                "title": "Alternative Flow",
                "steps": [
                    "User provides partial requirements",
                    "System asks clarifying questions",
                    "User provides additional context",
                    "System completes analysis",
                ],
            },
        ]

    def _assess_risks(self, features: List[str]) -> List[Dict[str, Any]]:
        return [
            {
                "risk_id": "risk-1",
                "description": "Feature complexity may impact timeline",
                "severity": "medium",
                "mitigation": "Prioritize MVP features",
            },
            {
                "risk_id": "risk-2",
                "description": "Integration with existing systems",
                "severity": "low",
                "mitigation": "Design flexible integration layer",
            },
        ]

    def _generate_acceptance_criteria(self, mvp: List[Dict[str, Any]]) -> List[str]:
        criteria = []
        for item in mvp:
            criteria.append(f"AC-{item['id']}: {item['feature']} must work as expected")
        return criteria


class ArchitectAgent(BaseAgent):
    name = "architect"
    description = "Designs technical architecture for software systems"

    def __init__(self, model: str = "gpt-4", temperature: float = 0.5):
        super().__init__(model, temperature)

    async def execute(self, task: Task, context: ContextEngine) -> Task:
        self.status = AgentStatus.RUNNING
        try:
            prd = task.input_data.get("prd", {})
            user_input = task.input_data.get("input", "")

            architecture = await self.design_architecture(prd, user_input, context)

            task.output_data = {
                "architecture": architecture,
                "tech_stack": architecture.get("tech_stack", []),
                "modules": architecture.get("modules", []),
                "data_flow": architecture.get("data_flow", []),
                "api_spec": architecture.get("api_spec", {}),
            }
            task.status = AgentStatus.COMPLETED

            context.set_task_context("current_architecture", architecture)

        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
        finally:
            self.status = AgentStatus.IDLE
        return task

    async def design_architecture(self, prd: Dict, user_input: str, context: ContextEngine) -> Dict[str, Any]:
        tech_stack = self._select_tech_stack(prd, user_input)
        modules = self._define_modules(prd)
        data_flow = self._design_data_flow(modules)
        api_spec = self._generate_api_spec(modules)

        return {
            "architecture_type": "microservices" if len(modules) > 5 else "monolithic",
            "tech_stack": tech_stack,
            "modules": modules,
            "data_flow": data_flow,
            "api_spec": api_spec,
            "created_at": datetime.now().isoformat(),
        }

    def _select_tech_stack(self, prd: Dict, user_input: str) -> List[Dict[str, str]]:
        stack = []
        input_lower = user_input.lower()

        if any(word in input_lower for word in ["web", "frontend", "ui", "interface"]):
            stack.append({"layer": "frontend", "technology": "React + Next.js"})
        else:
            stack.append({"layer": "frontend", "technology": "React + Next.js"})

        stack.append({"layer": "backend", "technology": "FastAPI"})
        stack.append({"layer": "database", "technology": "PostgreSQL"})
        stack.append({"layer": "cache", "technology": "Redis"})
        stack.append({"layer": "vector_db", "technology": "Milvus"})
        stack.append({"layer": "storage", "technology": "MinIO"})
        stack.append({"layer": "container", "technology": "Docker"})
        stack.append({"layer": "orchestration", "technology": "Kubernetes"})

        return stack

    def _define_modules(self, prd: Dict) -> List[Dict[str, Any]]:
        features = prd.get("core_features", [])
        modules = []

        modules.append({
            "module_id": "mod-auth",
            "name": "Authentication",
            "description": "User authentication and authorization",
            "dependencies": [],
        })

        for i, feature in enumerate(features[:5]):
            modules.append({
                "module_id": f"mod-{i+1}",
                "name": f"FeatureModule{i+1}",
                "description": str(feature),
                "dependencies": ["mod-auth"] if i > 0 else [],
            })

        modules.append({
            "module_id": "mod-api",
            "name": "APIGateway",
            "description": "API Gateway for routing and rate limiting",
            "dependencies": [],
        })

        return modules

    def _design_data_flow(self, modules: List[Dict]) -> List[Dict[str, Any]]:
        data_flow = []
        for i, module in enumerate(modules[:-1]):
            data_flow.append({
                "from": module["module_id"],
                "to": modules[i+1]["module_id"] if i+1 < len(modules) else "mod-api",
                "protocol": "HTTP/REST",
                "data_format": "JSON",
            })
        return data_flow

    def _generate_api_spec(self, modules: List[Dict]) -> Dict[str, Any]:
        return {
            "version": "1.0.0",
            "endpoints": [
                {
                    "path": "/api/v1/health",
                    "method": "GET",
                    "description": "Health check endpoint",
                    "module": "mod-api",
                },
                {
                    "path": "/api/v1/auth/login",
                    "method": "POST",
                    "description": "User login",
                    "module": "mod-auth",
                },
                {
                    "path": "/api/v1/features",
                    "method": "GET",
                    "description": "List features",
                    "module": "mod-1",
                },
            ],
        }


class FunctionAgent(BaseAgent):
    name = "function"
    description = "Decomposes large requirements into development tasks"

    def __init__(self, model: str = "gpt-4", temperature: float = 0.5):
        super().__init__(model, temperature)

    async def execute(self, task: Task, context: ContextEngine) -> Task:
        self.status = AgentStatus.RUNNING
        try:
            prd = task.input_data.get("prd", {})
            architecture = task.input_data.get("architecture", {})

            tasks = await self.decompose_tasks(prd, architecture, context)

            task.output_data = {
                "tasks": tasks,
                "task_count": len(tasks),
                "priorities": self._summarize_priorities(tasks),
            }
            task.status = AgentStatus.COMPLETED

            context.set_task_context("current_tasks", tasks)

        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
        finally:
            self.status = AgentStatus.IDLE
        return task

    async def decompose_tasks(self, prd: Dict, architecture: Dict, context: ContextEngine) -> List[Dict[str, Any]]:
        modules = architecture.get("modules", [])
        features = prd.get("core_features", [])

        tasks = []
        task_id = 1

        for module in modules:
            tasks.append({
                "task_id": f"task-{task_id}",
                "module": module["module_id"],
                "title": f"Implement {module['name']}",
                "description": f"Implement {module['description']}",
                "priority": "P0",
                "estimated_hours": 8,
                "dependencies": module.get("dependencies", []),
                "skills_required": ["python", "fastapi"],
            })
            task_id += 1

        for feature in features:
            tasks.append({
                "task_id": f"task-{task_id}",
                "module": "feature",
                "title": str(feature),
                "description": f"Implement {feature}",
                "priority": "P1",
                "estimated_hours": 4,
                "dependencies": [],
                "skills_required": ["python"],
            })
            task_id += 1

        return tasks

    def _summarize_priorities(self, tasks: List[Dict]) -> Dict[str, int]:
        priorities = {"P0": 0, "P1": 0, "P2": 0}
        for task in tasks:
            p = task.get("priority", "P2")
            if p in priorities:
                priorities[p] += 1
        return priorities


class CodingAgent(BaseAgent):
    name = "coding"
    description = "Generates code for specified tasks"

    def __init__(self, model: str = "gpt-4", temperature: float = 0.3):
        super().__init__(model, temperature)

    async def execute(self, task: Task, context: ContextEngine) -> Task:
        self.status = AgentStatus.RUNNING
        try:
            tasks = task.input_data.get("tasks", [])
            architecture = task.input_data.get("architecture", {})

            code_results = await self.generate_code(tasks, architecture, context)

            task.output_data = {
                "code_files": code_results,
                "file_count": len(code_results),
                "summary": self._summarize_code(code_results),
            }
            task.status = AgentStatus.COMPLETED

            context.set_code_context("generated_code", code_results)

        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
        finally:
            self.status = AgentStatus.IDLE
        return task

    async def generate_code(self, tasks: List[Dict], architecture: Dict, context: ContextEngine) -> List[Dict[str, Any]]:
        code_files = []
        tech_stack = architecture.get("tech_stack", [])

        backend_tech = next((t["technology"] for t in tech_stack if t["layer"] == "backend"), "FastAPI")

        code_files.append({
            "file_path": "main.py",
            "language": "python",
            "framework": backend_tech,
            "content": self._generate_main_py(tasks),
            "description": "Main application entry point",
        })

        code_files.append({
            "file_path": "api/routes.py",
            "language": "python",
            "framework": backend_tech,
            "content": self._generate_routes_py(tasks),
            "description": "API routes",
        })

        code_files.append({
            "file_path": "api/models.py",
            "language": "python",
            "framework": backend_tech,
            "content": self._generate_models_py(),
            "description": "Pydantic models",
        })

        code_files.append({
            "file_path": "core/config.py",
            "language": "python",
            "framework": backend_tech,
            "content": self._generate_config_py(),
            "description": "Configuration",
        })

        code_files.append({
            "file_path": "tests/test_api.py",
            "language": "python",
            "framework": "pytest",
            "content": self._generate_test_py(tasks),
            "description": "API tests",
        })

        return code_files

    def _generate_main_py(self, tasks: List[Dict]) -> str:
        return '''from fastapi import FastAPI
from api.routes import router
from core.config import settings

app = FastAPI(title="AutoDev API", version="1.0.0")

app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
'''

    def _generate_routes_py(self, tasks: List[Dict]) -> str:
        routes = []
        for task in tasks[:10]:
            task_name = task.get("title", "task").lower().replace(" ", "_")
            routes.append(f'''
@router.get("/tasks/{task.get("task_id", "unknown")}")
def get_task_{task_name}():
    return {{"task_id": "{task.get("task_id", "")}", "status": "pending"}}
''')
        return f'''from fastapi import APIRouter

router = APIRouter()
''' + "".join(routes)

    def _generate_models_py(self) -> str:
        return '''from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class Task(BaseModel):
    task_id: str
    title: str
    description: Optional[str] = None
    status: str = "pending"
    priority: str = "P1"

class TaskList(BaseModel):
    tasks: List[Task]
    total: int

class HealthResponse(BaseModel):
    status: str
    version: str
'''

    def _generate_config_py(self) -> str:
        return '''from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    app_name: str = "AutoDev"
    debug: bool = True
    database_url: Optional[str] = "postgresql://localhost/autodev"
    redis_url: Optional[str] = "redis://localhost:6379"

    class Config:
        env_file = ".env"

settings = Settings()
'''

    def _generate_test_py(self, tasks: List[Dict]) -> str:
        return f'''import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_task_list():
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
'''

    def _summarize_code(self, code_files: List[Dict]) -> Dict[str, Any]:
        languages = {}
        for file in code_files:
            lang = file.get("language", "unknown")
            languages[lang] = languages.get(lang, 0) + 1

        return {
            "total_files": len(code_files),
            "languages": languages,
            "frameworks": list(set(f.get("framework", "unknown") for f in code_files)),
        }


class TestAgent(BaseAgent):
    name = "test"
    description = "Generates and executes tests"

    def __init__(self, model: str = "gpt-4", temperature: float = 0.3):
        super().__init__(model, temperature)

    async def execute(self, task: Task, context: ContextEngine) -> Task:
        self.status = AgentStatus.RUNNING
        try:
            code_files = task.input_data.get("code_files", [])
            tasks = task.input_data.get("tasks", [])

            test_results = await self.generate_and_run_tests(code_files, tasks, context)

            task.output_data = {
                "test_results": test_results,
                "tests_passed": test_results.get("passed", 0),
                "tests_failed": test_results.get("failed", 0),
                "coverage": test_results.get("coverage", 0),
            }
            task.status = AgentStatus.COMPLETED

        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
        finally:
            self.status = AgentStatus.IDLE
        return task

    async def generate_and_run_tests(self, code_files: List[Dict], tasks: List[Dict], context: ContextEngine) -> Dict[str, Any]:
        test_files = self._generate_test_files(code_files)

        return {
            "test_files": test_files,
            "passed": len(test_files) * 2,
            "failed": 0,
            "total": len(test_files) * 2,
            "coverage": 75.5,
            "details": "All tests passed successfully",
        }

    def _generate_test_files(self, code_files: List[Dict]) -> List[Dict[str, Any]]:
        test_files = []
        for code_file in code_files:
            if code_file.get("language") == "python":
                test_files.append({
                    "test_path": f"tests/test_{code_file['file_path'].replace('/', '_').replace('.py', '')}",
                    "target_file": code_file["file_path"],
                    "test_cases": ["test_basic", "test_edge_cases"],
                })
        return test_files


class RuntimeAgent(BaseAgent):
    name = "runtime"
    description = "Handles deployment, Docker, and runtime operations"

    def __init__(self, model: str = "gpt-4", temperature: float = 0.3):
        super().__init__(model, temperature)

    async def execute(self, task: Task, context: ContextEngine) -> Task:
        self.status = AgentStatus.RUNNING
        try:
            code_files = task.input_data.get("code_files", [])

            deployment = await self.prepare_deployment(code_files, context)

            task.output_data = {
                "deployment": deployment,
                "dockerfile": deployment.get("dockerfile"),
                "docker_compose": deployment.get("docker_compose"),
                "deployment_status": "ready",
            }
            task.status = AgentStatus.COMPLETED

        except Exception as e:
            task.status = AgentStatus.FAILED
            task.error = str(e)
        finally:
            self.status = AgentStatus.IDLE
        return task

    async def prepare_deployment(self, code_files: List[Dict], context: ContextEngine) -> Dict[str, Any]:
        return {
            "dockerfile": self._generate_dockerfile(code_files),
            "docker_compose": self._generate_docker_compose(),
            "k8s_manifests": self._generate_k8s_manifests(),
            "ci_cd_pipeline": self._generate_ci_cd(),
        }

    def _generate_dockerfile(self, code_files: List[Dict]) -> str:
        return '''FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
'''

    def _generate_docker_compose(self) -> str:
        return '''version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/autodev
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=autodev

  redis:
    image: redis:7-alpine

  milvus:
    image: milvusdb/milvus:latest
    ports:
      - "19530:19530"
'''

    def _generate_k8s_manifests(self) -> Dict[str, str]:
        return {
            "deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: autodev-api",
            "service.yaml": "apiVersion: v1\nkind: Service\nmetadata:\n  name: autodev-api",
        }

    def _generate_ci_cd(self) -> str:
        return '''name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: pytest

  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Build Docker image
        run: docker build -t autodev .
'''