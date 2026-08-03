from __future__ import annotations

import hashlib
import json

import pytest

from app.core.config import Settings
from app.improvement.benchmark import CASES, ImprovementBenchmark
from app.improvement.forge import AdamForge
from app.improvement.service import ImprovementService
from app.lab_ui import LAB_UI
from app.storage.operations import OperationsStore


def _settings(tmp_path, **updates) -> Settings:
    return Settings(
        _env_file=None,
        workspace_root=tmp_path,
        local_embedding_enabled=False,
        improvement_database_path=tmp_path / "improvement.db",
        operations_database_path=tmp_path / "ops.db",
        **updates,
    )


def test_improvement_arena_has_40_varied_hidden_cases() -> None:
    result = ImprovementBenchmark().run()

    assert len(CASES) == 40
    assert {case.category for case in CASES} == {
        "patch",
        "retrieval",
        "router",
        "safety",
    }
    assert {"visible", "hidden", "adversarial"} <= {
        case.split for case in CASES
    }
    assert result["score"] == 100.0
    assert result["passed"] == result["total"] == 40


@pytest.mark.asyncio
async def test_verified_experience_becomes_fixed_budget_recall(tmp_path) -> None:
    service = ImprovementService(_settings(tmp_path))
    source = "def add(a, b):\n    return a + b\n"
    await service.remember_orientation(
        path="src/calc.py",
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        outline="def add(a, b)",
        relations=["tests/test_calc.py"],
    )
    episode_id = await service.record_verified_outcome(
        command_id="cmd-1",
        task_id="T1",
        goal="Build a calculator",
        title="Implement Python calculator add",
        verification="pytest -q",
        files=["src/calc.py"],
        evidence=[{"type": "test", "value": "pytest -q"}],
        success=True,
        route_key="local_qwen",
        model="qwen3",
    )

    capsule = await service.recall(
        query="Python calculator add pytest",
        target_path="src/calc.py",
        max_chars=900,
    )
    status = await service.status()

    assert episode_id
    assert "src/calc.py" in capsule.text
    assert len(capsule.text) <= 900
    assert status["episodes"] == 1
    assert status["strategies"] == 1
    assert status["orientation_entries"] == 2


@pytest.mark.asyncio
async def test_forge_requires_evaluation_and_explicit_promotion(tmp_path) -> None:
    settings = _settings(tmp_path)
    service = ImprovementService(settings)
    forge = AdamForge(settings=settings, improvement=service)
    candidate = await forge.create(
        kind="strategy",
        title="Exact verification",
        payload={"instruction": "Run the exact verification once."},
    )

    evaluated = await forge.evaluate(candidate["id"])
    assert evaluated["status"] == "evaluated"
    evaluation = json.loads(evaluated["evaluation_json"])
    assert evaluation["passed_gate"] is True
    assert evaluation["live_state_changed"] is False

    with pytest.raises(ValueError, match="explicit confirmation"):
        await forge.promote(candidate["id"], confirmation="yes")

    promoted = await forge.promote(
        candidate["id"],
        confirmation="PROMETHEUS ONAYLIYORUM",
    )
    assert promoted["status"] == "promoted"

    recall = await service.recall(query="verification")
    assert "ACTIVE_STRATEGY" in recall.text

    rolled_back = await forge.rollback(candidate["id"])
    assert rolled_back["status"] == "rolled_back"


@pytest.mark.asyncio
async def test_verified_task_router_statistics_round_trip(tmp_path) -> None:
    store = OperationsStore(tmp_path / "ops.db")
    await store.initialize()
    for success in (True, True, True, False):
        await store.record_verified_task_route(
            task_signature="a" * 20,
            route_key="local_qwen",
            success=success,
        )

    rows = await store.verified_task_route_stats("a" * 20)
    assert rows == [
        {
            "task_signature": "a" * 20,
            "route_key": "local_qwen",
            "verified_successes": 3,
            "verified_failures": 1,
            "total_latency_ms": 0,
            "total_output_tokens": 0,
            "updated_at": rows[0]["updated_at"],
        }
    ]


def test_lab_ui_exposes_mission_memory_forge_and_arena() -> None:
    for marker in (
        "Prometheus Forge",
        "Canlı Test",
        "Bellek & RAG",
        "40-vaka Improvement Arena",
        "/v1/improvement/benchmark/run",
        "/v1/supervisor/commands",
        "PROMETHEUS ONAYLIYORUM",
        "prometheus.activeCommandId",
        "adam.activeCommandId",
        "localStorage.removeItem('prometheus.activeCommandId')",
        "localStorage.removeItem('adam.activeCommandId')",
        "resumeLatestCommand",
        "liveActivityState",
        "liveHeartbeatAge",
        "Qwen3.5 4B → gerekirse 9B",
        "Donmadı — senden onay bekliyor",
    ):
        assert marker in LAB_UI

@pytest.mark.asyncio
async def test_workspace_index_omits_sensitive_files(tmp_path, monkeypatch) -> None:
    (tmp_path / "src.py").write_text("def visible(): pass", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=never-index", encoding="utf-8")
    (tmp_path / "credentials.json").write_text(
        '{"token":"never-index"}',
        encoding="utf-8",
    )
    (tmp_path / "secrets.yaml").write_text(
        "token: never-index",
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text("SECRET=", encoding="utf-8")
    service = ImprovementService(_settings(tmp_path))
    captured_paths: list[str] = []

    async def capture_orientation(**kwargs):
        captured_paths.append(kwargs["path"])
        return "captured"

    monkeypatch.setattr(service, "remember_orientation", capture_orientation)
    result = await service.index_workspace(build_embeddings=False)

    assert "src.py" in captured_paths
    assert ".env.example" not in captured_paths  # unsupported suffix, not a secret block
    assert ".env" not in captured_paths
    assert "credentials.json" not in captured_paths
    assert "secrets.yaml" not in captured_paths
    assert result["indexed_files"] == 1
