from pathlib import Path

import pytest

from app.core.config import Settings
from app.planning.integrity import validate_planning_document
from app.planning.kernel import TypedPlanningKernel
from app.tools.registry import build_default_tool_registry


@pytest.mark.asyncio
async def test_kernel_builds_python_and_react_test_graph(
    tmp_path: Path,
):
    (tmp_path / "app.py").write_text(
        "def topla(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    component = tmp_path / "src" / "components"
    component.mkdir(parents=True)
    (component / "TestButton.tsx").write_text(
        "export function TestButton(){ return <button>Test</button>; }\n",
        encoding="utf-8",
    )

    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    kernel = TypedPlanningKernel(tools=tools)

    result = await kernel.build(
        goal=(
            "Python fonksiyonu ve React bileşenleri için gerçek "
            "test altyapısı oluşturmayı planla."
        )
    )

    assert len(result.document.tasks) == 3
    assert result.document.tasks[0].assigned_agent == "backend"
    assert result.document.tasks[1].assigned_agent == "frontend"
    assert result.document.tasks[2].assigned_agent == "qa"
    assert result.document.tasks[0].dependencies == []
    assert result.document.tasks[1].dependencies == []
    assert result.document.tasks[2].dependencies == ["TASK-002"]

    integrity = validate_planning_document(
        result.document,
        known_paths={
            "app.py",
            "src/components/TestButton.tsx",
        },
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
    assert integrity.valid is True
    assert integrity.execution_layers[0] == ["TASK-001", "TASK-002"]
