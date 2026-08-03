from pathlib import Path

import pytest

from app.arena.catalog import get_scenario
from app.core.config import Settings
from app.planning.integrity import validate_planning_document
from app.planning.kernel import TypedPlanningKernel
from app.tools.registry import build_default_tool_registry


@pytest.mark.asyncio
async def test_single_html_calculator_has_concrete_safety_criteria(
    tmp_path: Path,
):
    tools = build_default_tool_registry(settings=Settings(workspace_root=tmp_path))
    kernel = TypedPlanningKernel(tools=tools)
    result = await kernel.build(
        goal="Tek bir HTML dosyasında dört işlem ve ondalık sayı destekleyen hesap makinesi oluştur."
    )

    task = result.document.tasks[0]
    criteria = " ".join(task.acceptance_criteria)
    assert task.exact_files == ["calculator.html"]
    assert "eval veya Function" in criteria
    assert "birden fazla ondalık" in criteria
    assert "3D görseller" not in criteria


@pytest.mark.asyncio
async def test_explicit_3b_planet_html_is_planned_without_redundant_question(
    tmp_path: Path,
):
    tools = build_default_tool_registry(settings=Settings(workspace_root=tmp_path))
    kernel = TypedPlanningKernel(tools=tools)
    result = await kernel.build(
        goal=(
            "workspace icinde prometheus-otonom-gezegen.html adli tek dosyada "
            "calisan etkilesimli bir 3B gezegen olustur"
        )
    )

    assert result.document.critical_decisions == []
    assert result.document.tasks[0].assigned_agent == "frontend"
    assert result.document.tasks[0].exact_files == [
        "prometheus-otonom-gezegen.html"
    ]


@pytest.mark.asyncio
async def test_empty_workspace_calculator_builds_runnable_web_graph(
    tmp_path: Path,
):
    tools = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    kernel = TypedPlanningKernel(tools=tools)
    result = await kernel.build(
        goal="Basit bir web hesap makinesi yap."
    )

    assert result.document.critical_decisions == []
    assert [task.assigned_agent for task in result.document.tasks] == [
        "frontend",
        "integration",
    ]
    assert result.document.tasks[0].exact_files == [
        "package.json",
        "index.html",
        "styles.css",
        "src/app.js",
        "src/calculator.js",
        "tests/calculator.test.js",
    ]
    assert result.document.tasks[0].verification == "npm test"
    assert result.document.tasks[1].dependencies == ["TASK-001"]
    assert result.document.tasks[1].verification == "npm run build"

    integrity = validate_planning_document(
        result.document,
        known_paths=set(),
        known_agents={
            "worker",
            "frontend",
            "backend",
            "database",
            "qa",
            "architect",
            "reviewer",
            "integration",
            "calculation",
            "planner",
        },
    )
    assert integrity.valid is True, integrity.errors


@pytest.mark.asyncio
async def test_dependency_free_calculator_uses_node_native_contract(
    tmp_path: Path,
):
    tools = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    kernel = TypedPlanningKernel(tools=tools)
    scenario = get_scenario("calculator_from_scratch")

    result = await kernel.build(goal=scenario.goal)

    criteria = result.document.tasks[0].acceptance_criteria
    assert any(
        "dependencies/devDependencies eklenmemeli" in item
        for item in criteria
    )
    assert any("node:test" in item for item in criteria)
    assert all("Vite tabanlı" not in item for item in criteria)


@pytest.mark.asyncio
async def test_calculator_request_compiles_to_concrete_react_files(tmp_path: Path):
    component = tmp_path / "src/components/TestButton.tsx"
    component.parent.mkdir(parents=True)
    component.write_text("export const TestButton = () => null", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest --run"}}', encoding="utf-8"
    )

    tools = build_default_tool_registry(settings=Settings(workspace_root=tmp_path))
    kernel = TypedPlanningKernel(tools=tools)
    result = await kernel.build(goal="bana bi hesap makinesi uygulaması yapsana")

    assert len(result.document.tasks) == 1
    task = result.document.tasks[0]
    assert task.assigned_agent == "frontend"
    assert task.exact_files == [
        "src/components/Calculator.tsx",
        "src/components/Calculator.test.tsx",
    ]
    assert task.verification == "npm test -- --run"
    assert "Kullanıcı hedefini workspace üzerinde uygula" not in result.text


@pytest.mark.asyncio
async def test_vanilla_app_ignores_stray_tsx_when_manifest_is_not_react(
    tmp_path: Path,
):
    (tmp_path / "src/components").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "src/components/OldCalculator.tsx").write_text(
        "export const OldCalculator = () => null",
        encoding="utf-8",
    )
    (tmp_path / "src/app.js").write_text("export {}", encoding="utf-8")
    (tmp_path / "src/calculator.js").write_text(
        "export const add = (a, b) => a + b",
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text("<main></main>", encoding="utf-8")
    (tmp_path / "styles.css").write_text("main {}", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"node --test","build":"vite build"},'
        '"devDependencies":{"vite":"^4.0.0"}}',
        encoding="utf-8",
    )

    tools = build_default_tool_registry(
        settings=Settings(workspace_root=tmp_path)
    )
    kernel = TypedPlanningKernel(tools=tools)
    result = await kernel.build(goal="bana bir hesap makinesi yap")

    assert result.document.tasks[0].exact_files == [
        "package.json",
        "index.html",
        "styles.css",
        "src/app.js",
        "src/calculator.js",
        "tests/calculator.test.js",
    ]
    assert result.document.tasks[0].verification == "npm test"
    assert all(
        not path.endswith(".tsx")
        for task in result.document.tasks
        for path in task.exact_files
    )


@pytest.mark.asyncio
async def test_unknown_mutating_goal_stops_at_decision_not_generic_worker(tmp_path: Path):
    (tmp_path / "app.py").write_text("x = 1", encoding="utf-8")
    tools = build_default_tool_registry(settings=Settings(workspace_root=tmp_path))
    kernel = TypedPlanningKernel(tools=tools)
    result = await kernel.build(goal="şunu daha iyi hale getir")

    assert result.document.critical_decisions
    assert result.document.tasks[0].assigned_agent == "planner"
    assert result.document.tasks[0].user_approval == "gerekmez"

    integrity = validate_planning_document(
        result.document,
        known_paths={"app.py"},
        known_agents={"planner"},
    )
    assert integrity.valid is True, integrity.errors
