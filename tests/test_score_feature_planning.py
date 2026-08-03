from pathlib import Path

import pytest

from app.core.config import Settings
from app.planning.kernel import TypedPlanningKernel
from app.tools.registry import build_default_tool_registry


@pytest.mark.asyncio
async def test_explicit_score_feature_is_planned_as_real_feature(
    tmp_path: Path,
):
    (tmp_path / "app.py").write_text(
        "def topla(a,b): return a+b\n",
        encoding="utf-8",
    )
    component = tmp_path / "src" / "components"
    component.mkdir(parents=True)
    (component / "OldButton.tsx").write_text(
        "export function OldButton(){return <button/>}\n",
        encoding="utf-8",
    )
    (tmp_path / "package.json").write_text(
        '{"scripts":{"test":"vitest"}}',
        encoding="utf-8",
    )

    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    kernel = TypedPlanningKernel(tools=tools)

    result = await kernel.build(
        goal="""
        score.py dosyasında calculate_score(base, multiplier, bonus)
        fonksiyonunu oluştur.
        src/components/ScoreCard.tsx bileşenini oluştur.
        Python ve React testlerini çalıştır.
        """
    )

    assert len(result.document.tasks) == 2
    assert result.document.tasks[0].assigned_agent == "backend"
    assert result.document.tasks[1].assigned_agent == "frontend"
    assert "score.py" in result.document.tasks[0].title
    assert "ScoreCard.tsx" in result.document.tasks[1].title
    assert all(task.dependencies == [] for task in result.document.tasks)
    assert result.document.tasks[0].exact_files == [
        "score.py", "tests/test_score.py"
    ]
    assert result.document.tasks[1].exact_files == [
        "src/components/ScoreCard.tsx",
        "src/components/ScoreCard.test.tsx",
    ]
