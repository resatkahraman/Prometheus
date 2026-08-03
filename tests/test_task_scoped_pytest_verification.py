from __future__ import annotations

from pathlib import Path

import pytest

from app.arena.catalog import get_scenario
from app.arena.runner import ArenaRunner
from app.core.config import Settings
from app.planning.kernel import TypedPlanningKernel
from app.supervisor.models import SupervisorCommand
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


_BACKEND_SOURCE = '''from __future__ import annotations

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field, field_validator


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized


class TaskItem(BaseModel):
    id: int
    title: str
    completed: bool


def create_app() -> FastAPI:
    application = FastAPI()
    tasks: list[TaskItem] = []

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/tasks", response_model=list[TaskItem])
    def list_tasks() -> list[TaskItem]:
        return tasks

    @application.post(
        "/tasks",
        response_model=TaskItem,
        status_code=status.HTTP_201_CREATED,
    )
    def create_task(payload: TaskCreate) -> TaskItem:
        task = TaskItem(
            id=len(tasks) + 1,
            title=payload.title,
            completed=False,
        )
        tasks.append(task)
        return task

    @application.patch(
        "/tasks/{task_id}/complete",
        response_model=TaskItem,
    )
    def complete_task(task_id: int) -> TaskItem:
        for index, task in enumerate(tasks):
            if task.id == task_id:
                completed = task.model_copy(
                    update={"completed": True}
                )
                tasks[index] = completed
                return completed
        raise HTTPException(
            status_code=404,
            detail="Task not found",
        )

    return application


app = create_app()
'''


_QA_SOURCE = '''from fastapi.testclient import TestClient

from src.task_api import create_app


def test_health_and_empty_list():
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/tasks").json() == []


def test_create_and_list_in_order():
    client = TestClient(create_app())
    first = client.post("/tasks", json={"title": "  one "})
    second = client.post("/tasks", json={"title": "two"})
    assert first.status_code == 201
    assert second.status_code == 201
    assert client.get("/tasks").json() == [
        first.json(),
        second.json(),
    ]


def test_complete_and_missing_task():
    client = TestClient(create_app())
    client.post("/tasks", json={"title": "one"})
    completed = client.patch("/tasks/1/complete")
    assert completed.json()["completed"] is True
    assert client.patch("/tasks/404/complete").status_code == 404


def test_title_validation():
    client = TestClient(create_app())
    blank = client.post("/tasks", json={"title": "   "})
    too_long = client.post("/tasks", json={"title": "x" * 121})
    assert blank.status_code == 422
    assert too_long.status_code == 422
'''


@pytest.mark.asyncio
async def test_backend_contract_can_pass_before_dependent_qa_file_exists(
    tmp_path: Path,
):
    scenario = get_scenario("fastapi_task_api")
    ArenaRunner._seed(tmp_path, scenario)
    (tmp_path / "src/task_api.py").write_text(
        _BACKEND_SOURCE,
        encoding="utf-8",
    )

    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    planner = TypedPlanningKernel(tools=tools, read_max_lines=160)
    planning = await planner.build(goal=scenario.goal)
    backend_plan, qa_plan = planning.document.tasks

    backend = SupervisorService._task_from_plan(backend_plan)
    arguments = SupervisorService._verification_arguments(backend)

    assert arguments == {
        "preset": "pytest",
        "extra_args": ["tests/test_task_api_backend_contract.py"],
    }

    backend_result = await tools.execute_direct(
        "safe_terminal",
        arguments,
    )
    assert backend_result["success"] is True
    assert "3 passed" in str(backend_result.get("stdout") or "")

    full_result = await tools.execute_direct(
        "safe_terminal",
        {"preset": "pytest", "extra_args": []},
    )
    assert full_result["success"] is False
    assert "test_qa_suite_is_material" in "\n".join(
        str(full_result.get(key) or "")
        for key in ("stdout", "stderr")
    )

    backend.status = "completed"
    qa = SupervisorService._task_from_plan(qa_plan)
    qa.status = "blocked"
    command = SupervisorCommand(
        id="cmd-scoped-pytest",
        goal=scenario.goal,
        status="ready",
        plan_text="",
        tasks=[backend, qa],
    )
    SupervisorService._refresh_task_states(command)

    assert command.tasks[1].status == "ready"

    (tmp_path / "tests/test_task_api.py").write_text(
        _QA_SOURCE,
        encoding="utf-8",
    )
    completed = await tools.execute_direct(
        "safe_terminal",
        {"preset": "pytest", "extra_args": []},
    )
    assert completed["success"] is True
    assert "8 passed" in str(completed.get("stdout") or "")
