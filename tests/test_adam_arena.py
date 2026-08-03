from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.arena.catalog import get_scenario, list_scenarios, validate_scenario
from app.arena.models import (
    ArenaResult,
    ArenaScenario,
    ArenaScore,
    ArenaVerification,
)
from app.arena.runner import ArenaRunner, _safe_workspace_path
from app.arena.scoring import score_arena_run
from app.arena.store import ArenaStore
from app.arena.suite import build_suite_report, render_suite_markdown
from app.arena.usage import summarize_usage
from app.core.config import Settings
from app.tools.registry import build_default_tool_registry
from scripts.run_real_world_suite import QUICK_SCENARIOS


def test_catalog_is_valid_and_paths_are_confined(tmp_path: Path):
    scenarios = list_scenarios()

    assert {item.id for item in scenarios} == {
        "calculator_from_scratch",
        "existing_vanilla_repair",
        "fastapi_status_contract_repair",
        "fastapi_task_api",
        "js_bugfix",
        "multi_agent_delivery",
        "python_feature",
        "test_authoring",
    }
    assert get_scenario("JS_BUGFIX").id == "js_bugfix"
    assert _safe_workspace_path(tmp_path, "src/app.js") == (
        tmp_path / "src/app.js"
    ).resolve()
    with pytest.raises(ValueError, match="Güvensiz"):
        _safe_workspace_path(tmp_path, "../outside.txt")


def test_real_world_calculator_scenario_covers_short_request_and_delivery():
    scenario = get_scenario("calculator_from_scratch")

    assert scenario.initial_verification_should_fail is True
    assert scenario.required_agents == ("frontend", "integration")
    assert scenario.minimum_handoffs == 4
    assert {
        "package.json",
        "index.html",
        "styles.css",
        "src/app.js",
        "src/calculator.js",
        "tests/calculator.test.js",
    } == set(scenario.required_paths)
    assert scenario.protected_paths == (
        "test/real-world.contract.test.js",
    )
    assert {item.preset for item in scenario.verifications} == {
        "node_test",
        "node_check",
    }


def test_real_world_vanilla_repair_protects_project_shape():
    scenario = get_scenario("existing_vanilla_repair")

    assert scenario.required_paths == ("src/calculator.js",)
    assert "src/components/LegacyCalculator.tsx" in scenario.protected_paths
    assert "package.json" in scenario.protected_paths
    assert "test/calculator.contract.test.js" in scenario.protected_paths


def test_fastapi_task_api_scenario_measures_backend_qa_delivery():
    scenario = get_scenario("fastapi_task_api")

    assert scenario.initial_verification_should_fail is True
    assert scenario.required_agents == ("backend", "qa")
    assert "fastapi_task_api" in QUICK_SCENARIOS
    assert scenario.minimum_handoffs == 4
    assert scenario.required_paths == (
        "src/task_api.py",
        "tests/test_task_api.py",
    )
    assert scenario.protected_paths == (
        "src/__init__.py",
        "pyproject.toml",
        "tests/test_task_api_backend_contract.py",
        "tests/test_task_api_delivery_contract.py",
    )
    assert len(scenario.verifications) == 1
    assert scenario.verifications[0].preset == "pytest"
    backend_contract = scenario.seed_files[
        "tests/test_task_api_backend_contract.py"
    ]
    delivery_contract = scenario.seed_files[
        "tests/test_task_api_delivery_contract.py"
    ]
    assert 'client.post("/tasks"' in backend_contract
    assert 'client.patch("/tasks/999/complete")' in backend_contract
    assert "tests/test_task_api.py" not in backend_contract
    assert "len(test_functions) >= 4" in delivery_contract


@pytest.mark.asyncio
async def test_fastapi_task_api_contract_is_red_then_green(
    tmp_path: Path,
):
    scenario = get_scenario("fastapi_task_api")
    ArenaRunner._seed(tmp_path, scenario)
    protected_before = {
        path: (tmp_path / path).read_bytes()
        for path in scenario.protected_paths
    }

    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    verification = scenario.verifications[0]
    arguments = {
        "preset": verification.preset,
        "extra_args": list(verification.extra_args),
    }

    baseline = await tools.execute_direct("safe_terminal", arguments)
    baseline_output = "\n".join(
        str(baseline.get(key) or "")
        for key in ("stdout", "stderr")
    )
    assert baseline["success"] is False
    assert baseline["exit_code"] == 2
    assert "src.task_api" in baseline_output

    (tmp_path / "src/task_api.py").write_text(
        '''from __future__ import annotations

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
''',
        encoding="utf-8",
    )
    (tmp_path / "tests/test_task_api.py").write_text(
        '''from fastapi.testclient import TestClient

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
''',
        encoding="utf-8",
    )

    completed = await tools.execute_direct("safe_terminal", arguments)
    assert completed["success"] is True
    assert completed["exit_code"] == 0
    assert "8 passed" in str(completed.get("stdout") or "")
    assert {
        path: (tmp_path / path).read_bytes()
        for path in scenario.protected_paths
    } == protected_before


def test_real_world_suite_requires_every_independent_gate():
    passing = {
        "scenario_id": "passing",
        "scenario_title": "Passing",
        "status": "completed",
        "failure_reason": None,
        "elapsed_seconds": 2.5,
        "required_paths_ok": True,
        "protected_paths_ok": True,
        "verifications": [{"success": True}],
        "coordination": {"work_sharing_ok": True},
        "usage": {"model_calls": 2, "total_tokens": 300},
        "score": {"total": 99},
        "workspace": "one",
    }
    failing = {
        **passing,
        "scenario_id": "failing",
        "protected_paths_ok": False,
        "usage": {"model_calls": 1, "total_tokens": 100},
    }

    report = build_suite_report(
        [passing, failing],
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:05+00:00",
        local_only=True,
    )
    markdown = render_suite_markdown(report)

    assert report["success"] is False
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["model_calls"] == 3
    assert report["total_tokens"] == 400
    assert report["results"][1]["gates"]["protected_paths"] is False
    assert "1/2 geçti" in markdown


def test_catalog_rejects_protected_path_without_seed():
    scenario = ArenaScenario(
        id="invalid",
        title="Invalid",
        goal="A valid goal",
        seed_files={"source.py": ""},
        required_paths=("source.py",),
        protected_paths=("tests/test_source.py",),
        verifications=(
            ArenaVerification(name="tests", preset="pytest"),
        ),
        max_model_calls=5,
        max_estimated_input_tokens=5_000,
        target_model_calls=3,
        target_total_tokens=3_000,
    )

    with pytest.raises(ValueError, match="Korunan yollar"):
        validate_scenario(scenario)


def test_local_only_arena_overrides_remote_keys_from_env_file(
    tmp_path: Path,
):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".env").write_text(
        "\n".join(
            [
                "GEMINI_API_KEY=test-gemini",
                "GITHUB_TOKEN=test-github",
                "GROQ_API_KEY=test-groq",
            ]
        ),
        encoding="utf-8",
    )
    runner = ArenaRunner(
        project_root=project,
        workspace_root=project / "workspace",
        local_only=True,
    )

    settings = runner._settings(
        workspace=project / "workspace" / "proof",
        scenario=get_scenario("js_bugfix"),
    )

    assert settings.gemini_api_key is None
    assert settings.github_token is None
    assert settings.groq_api_key is None
    assert settings.supervisor_trusted_autonomy_enabled is True
    assert settings.operations_database_path == (
        project / "workspace" / "proof" / ".adam" / "operations.db"
    )


def test_arena_detects_ready_command_without_runnable_work():
    blocked = SimpleNamespace(
        tasks=[
            SimpleNamespace(
                status="rework_required",
                blocked_reason="same failure",
            )
        ]
    )
    runnable = SimpleNamespace(
        tasks=[
            SimpleNamespace(status="ready", blocked_reason=None)
        ]
    )

    assert ArenaRunner._has_runnable_work(blocked) is False
    assert ArenaRunner._has_runnable_work(runnable) is True


def test_arena_score_rewards_verified_autonomous_efficient_completion():
    scenario = get_scenario("js_bugfix")

    perfect = score_arena_run(
        scenario=scenario,
        status="completed",
        verification_passed=1,
        verification_total=1,
        required_paths_ok=True,
        protected_paths_ok=True,
        approvals=0,
        decisions=0,
        model_calls=scenario.target_model_calls,
        total_tokens=scenario.target_total_tokens,
        failed_calls=0,
        task_attempts=1,
        task_count=1,
        failure_records=0,
    )
    degraded = score_arena_run(
        scenario=scenario,
        status="failed",
        verification_passed=0,
        verification_total=1,
        required_paths_ok=True,
        protected_paths_ok=False,
        approvals=2,
        decisions=1,
        model_calls=scenario.target_model_calls * 2,
        total_tokens=scenario.target_total_tokens * 2,
        failed_calls=2,
        task_attempts=3,
        task_count=1,
        failure_records=2,
    )

    assert perfect.total == 100.0
    assert degraded.total < 20
    assert degraded.total <= 60


def test_arena_score_caps_fake_multi_agent_completion():
    scenario = get_scenario("multi_agent_delivery")

    score = score_arena_run(
        scenario=scenario,
        status="completed",
        verification_passed=1,
        verification_total=1,
        required_paths_ok=True,
        protected_paths_ok=True,
        approvals=0,
        decisions=0,
        model_calls=scenario.target_model_calls,
        total_tokens=scenario.target_total_tokens,
        failed_calls=0,
        task_attempts=3,
        task_count=3,
        failure_records=0,
        work_sharing_ok=False,
    )

    assert score.total == 70.0


def test_arena_coordination_requires_completed_role_handoffs():
    scenario = get_scenario("multi_agent_delivery")
    tasks = [
        SimpleNamespace(assigned_agent=agent, status="completed")
        for agent in scenario.required_agents
    ]
    handoffs = []
    for index, agent in enumerate(scenario.required_agents, start=1):
        handoffs.extend(
            [
                SimpleNamespace(
                    type="task_assignment",
                    to_agent=agent,
                    from_agent="supervisor",
                ),
                SimpleNamespace(
                    type="completion",
                    to_agent="supervisor",
                    from_agent=agent,
                ),
            ]
        )
    command = SimpleNamespace(
        tasks=tasks,
        handoffs=handoffs,
        execution_layers=[
            ["TASK-001"],
            ["TASK-002"],
            ["TASK-003"],
        ],
    )

    coordination = ArenaRunner._coordination(command, scenario)

    assert coordination["work_sharing_ok"] is True
    assert coordination["distinct_completed_agents"] == 3
    assert coordination["handoff_count"] == 6


def test_arena_store_persists_full_result(tmp_path: Path):
    store = ArenaStore(tmp_path / "arena.db")
    result = ArenaResult(
        run_id="run-1",
        scenario_id="js_bugfix",
        scenario_title="JS",
        mission_id="mission-1",
        status="completed",
        failure_reason=None,
        elapsed_seconds=1.25,
        workspace=str(tmp_path),
        approvals_applied=0,
        decisions_answered=0,
        required_paths_ok=True,
        missing_required_paths=[],
        protected_paths_ok=True,
        changed_protected_paths=[],
        baseline_verifications=[],
        verifications=[],
        usage={"events": 2, "total_tokens": 300},
        mission_usage=None,
        task_attempts=1,
        failure_records=0,
        score=ArenaScore(
            total=95,
            completion=40,
            verification=25,
            artifacts=10,
            autonomy=10,
            efficiency=5,
            reliability=5,
        ),
    )

    store.record(result)
    rows = store.history(scenario_id="js_bugfix")

    assert len(rows) == 1
    assert rows[0]["score"] == 95
    assert json.loads(rows[0]["result_json"])["mission_id"] == "mission-1"


def test_usage_summary_is_scoped_and_tolerates_bad_lines(tmp_path: Path):
    usage_log = tmp_path / "usage.jsonl"
    usage_log.write_text(
        "\n".join(
            [
                "{bad-json",
                json.dumps(
                    {
                        "usage_scope": "mission-a",
                        "provider": "github",
                        "success": True,
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "latency_ms": 50,
                    }
                ),
                json.dumps(
                    {
                        "usage_scope": "mission-b",
                        "provider": "gemini",
                        "success": True,
                        "input_tokens": 999,
                    }
                ),
                json.dumps(
                    {
                        "usage_scope": "mission-a",
                        "provider": "groq",
                        "success": False,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latency_ms": 10,
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_usage(
        usage_log=usage_log,
        mission_id="mission-a",
    )

    assert summary["events"] == 2
    assert summary["successful_calls"] == 1
    assert summary["failed_calls"] == 1
    assert summary["total_tokens"] == 120
    assert summary["local_calls"] == 0
    assert summary["local_tokens"] == 0
    assert summary["remote_calls"] == 2
    assert summary["remote_tokens"] == 120


@pytest.mark.asyncio
async def test_quota_plan_preserves_configured_free_reserve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runner = ArenaRunner(
        project_root=tmp_path,
        workspace_root=tmp_path / "workspace",
    )
    scenario = get_scenario("js_bugfix")
    settings = Settings(
        _env_file=None,
        local_model_enabled=False,
        workspace_root=tmp_path / "probe",
        operations_database_path=tmp_path / "operations.db",
        usage_log_path=tmp_path / "usage.jsonl",
        github_token="test-token",
        gemini_api_key=None,
        groq_api_key=None,
        github_daily_request_budget=10,
        free_quota_conserve_ratio=0.2,
        mission_max_model_calls=scenario.max_model_calls,
        mission_max_estimated_input_tokens=(
            scenario.max_estimated_input_tokens
        ),
    )
    monkeypatch.setattr(
        runner,
        "_settings",
        lambda **_: settings,
    )

    plan = await runner.quota_plan(scenario)

    assert plan.allowed is True
    assert plan.usable_calls == 8
    assert len(plan.routes) == 1
    assert plan.routes[0].reserved == 2
