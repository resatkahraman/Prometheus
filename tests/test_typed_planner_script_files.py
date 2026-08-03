from __future__ import annotations

from pathlib import Path

import pytest

from app.approvals.manager import ApprovalManager
from app.arena.catalog import get_scenario
from app.core.config import Settings
from app.planning.kernel import TypedPlanningKernel
from app.tools.registry import build_default_tool_registry


@pytest.mark.asyncio
async def test_typed_planner_compiles_explicit_javascript_file_task(
    tmp_path: Path,
):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "discount.js").write_text(
        "export const discountedPrice = () => 0;\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"type":"module","scripts":{"test":"node --test"}}',
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(
        settings=settings,
        approvals=ApprovalManager(ttl_seconds=300),
    )
    kernel = TypedPlanningKernel(tools=tools, read_max_lines=120)

    result = await kernel.build(
        goal=(
            "src/discount.js dosyasındaki yüzde hesaplama hatasını düzelt. "
            "Yalnızca bu kaynak dosyasını değiştir, mevcut testleri değiştirme "
            "ve npm test komutunu geçir."
        ),
        decision_answers=None,
    )

    assert result.document.critical_decisions == []
    assert len(result.document.tasks) == 1
    task = result.document.tasks[0]
    assert task.assigned_agent == "backend"
    assert task.exact_files == ["src/discount.js"]
    assert task.verification == "npm test"
    assert any(
        item.type == "file" and item.value == "src/discount.js"
        for item in task.evidence
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_id", "agent_id", "expected_files"),
    [
        ("python_feature", "backend", ["text_stats.py"]),
        (
            "test_authoring",
            "qa",
            ["tests/test_slugify.py"],
        ),
    ],
)
async def test_typed_planner_respects_arena_python_write_contracts(
    tmp_path: Path,
    scenario_id: str,
    agent_id: str,
    expected_files: list[str],
):
    scenario = get_scenario(scenario_id)
    for relative, content in scenario.seed_files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    kernel = TypedPlanningKernel(tools=tools, read_max_lines=120)

    result = await kernel.build(goal=scenario.goal)

    assert result.document.critical_decisions == []
    assert len(result.document.tasks) == 1
    task = result.document.tasks[0]
    assert task.assigned_agent == agent_id
    assert task.exact_files == expected_files
    assert set(task.exact_files).isdisjoint(
        scenario.protected_paths
    )


@pytest.mark.asyncio
async def test_typed_planner_splits_fastapi_backend_and_qa_contract(
    tmp_path: Path,
):
    scenario = get_scenario("fastapi_task_api")
    for relative, content in scenario.seed_files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    kernel = TypedPlanningKernel(tools=tools, read_max_lines=160)

    result = await kernel.build(goal=scenario.goal)

    assert result.document.critical_decisions == []
    assert len(result.document.tasks) == 2

    backend, qa = result.document.tasks
    assert backend.id == "TASK-001"
    assert backend.assigned_agent == "backend"
    assert backend.exact_files == ["src/task_api.py"]
    assert backend.dependencies == []
    assert backend.verification == (
        "python -m pytest -q "
        "tests/test_task_api_backend_contract.py"
    )
    assert any(
        item.type == "file"
        and item.value == "tests/test_task_api_backend_contract.py"
        for item in backend.evidence
    )

    assert qa.id == "TASK-002"
    assert qa.assigned_agent == "qa"
    assert qa.exact_files == ["tests/test_task_api.py"]
    assert qa.dependencies == [backend.id]
    assert qa.parallelizable == "hayır"
    assert qa.verification == "python -m pytest -q"

    planned_files = {
        path
        for task in result.document.tasks
        for path in task.exact_files
    }
    assert planned_files.isdisjoint(scenario.protected_paths)


@pytest.mark.asyncio
async def test_protected_legacy_tsx_is_not_mistaken_for_a_target(
    tmp_path: Path,
):
    scenario = get_scenario("existing_vanilla_repair")
    for relative, content in scenario.seed_files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    kernel = TypedPlanningKernel(tools=tools, read_max_lines=120)

    result = await kernel.build(goal=scenario.goal)

    assert result.document.critical_decisions == []
    assert len(result.document.tasks) == 1
    assert result.document.tasks[0].assigned_agent == "backend"
    assert result.document.tasks[0].exact_files == ["src/calculator.js"]
    assert all(
        "LegacyCalculator" not in path
        for task in result.document.tasks
        for path in task.exact_files
    )


@pytest.mark.asyncio
async def test_typed_planner_builds_multi_agent_script_handoffs(
    tmp_path: Path,
):
    scenario = get_scenario("multi_agent_delivery")
    for relative, content in scenario.seed_files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        supervisor_persistence_enabled=False,
    )
    tools = build_default_tool_registry(settings=settings)
    kernel = TypedPlanningKernel(tools=tools, read_max_lines=120)

    result = await kernel.build(goal=scenario.goal)

    assert result.document.critical_decisions == []
    assert [task.assigned_agent for task in result.document.tasks] == [
        "backend",
        "frontend",
        "qa",
    ]
    assert [
        task.exact_files for task in result.document.tasks
    ] == [
        ["src/pricing.js"],
        ["src/view-model.js"],
        ["test/edge-cases.test.js"],
    ]
    assert result.document.tasks[0].dependencies == []
    assert result.document.tasks[1].dependencies == ["TASK-001"]
    assert result.document.tasks[2].dependencies == [
        "TASK-001",
        "TASK-002",
    ]
    assert result.document.tasks[0].verification == (
        "npm test -- test/pricing.contract.test.js"
    )
    assert result.document.tasks[1].verification == (
        "npm test -- test/view-model.contract.test.js"
    )
    assert result.document.tasks[2].verification == "npm test"
