from pathlib import Path

import pytest

from app.approvals.manager import ApprovalManager
from app.core.config import Settings
from app.tools.base import ToolApprovalRequired, ToolError
from app.tools.registry import build_default_tool_registry


def make_registry(tmp_path: Path):
    settings = Settings(
        workspace_root=tmp_path,
        workspace_max_file_bytes=100_000,
        workspace_max_search_results=20,
    )
    return build_default_tool_registry(
        settings=settings,
        approvals=ApprovalManager(ttl_seconds=300),
    )


@pytest.mark.asyncio
async def test_list_read_and_search(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "def login():\n    return 'ok'\n",
        encoding="utf-8",
    )
    registry = make_registry(tmp_path)

    listed = await registry.execute("workspace_list", {"path": "."})
    assert any(item["path"] == "src/app.py" for item in listed["entries"])

    read = await registry.execute(
        "workspace_read",
        {"path": "src/app.py"},
    )
    assert "login" in read["content"]

    searched = await registry.execute(
        "workspace_search",
        {"query": "login"},
    )
    assert searched["results"][0]["path"] == "src/app.py"


@pytest.mark.asyncio
async def test_write_requires_approval_and_creates_file(tmp_path):
    registry = make_registry(tmp_path)

    with pytest.raises(ToolApprovalRequired) as captured:
        await registry.execute(
            "workspace_write",
            {
                "path": "hello.txt",
                "content": "Adam",
            },
        )

    assert not (tmp_path / "hello.txt").exists()
    action_id = captured.value.pending.id
    result = await registry.execute_approved(action_id)

    assert result["changed"] is True
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "Adam"

@pytest.mark.asyncio
async def test_sensitive_files_are_hidden_from_workspace_tools(tmp_path):
    (tmp_path / ".env").write_text(
        "PROMETHEUS_SECRET=never-expose-this",
        encoding="utf-8",
    )
    (tmp_path / "credentials.json").write_text(
        '{"token":"never-expose-this"}',
        encoding="utf-8",
    )
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "id_rsa").write_text(
        "PRIVATE KEY never-expose-this",
        encoding="utf-8",
    )
    (tmp_path / ".env.example").write_text(
        "PROMETHEUS_SECRET=",
        encoding="utf-8",
    )
    (tmp_path / "src.py").write_text(
        "VISIBLE_MARKER = 'safe'",
        encoding="utf-8",
    )
    registry = make_registry(tmp_path)

    listed = await registry.execute("workspace_list", {"path": ".", "depth": 6})
    listed_paths = {entry["path"] for entry in listed["entries"]}
    assert ".env" not in listed_paths
    assert "credentials.json" not in listed_paths
    assert ".ssh" not in listed_paths
    assert ".ssh/id_rsa" not in listed_paths
    assert ".env.example" in listed_paths
    assert "src.py" in listed_paths

    for sensitive_path in (".env", "credentials.json", ".ssh/id_rsa"):
        with pytest.raises(ToolError, match="Hassas"):
            await registry.execute("workspace_read", {"path": sensitive_path})

    secret_search = await registry.execute(
        "workspace_search",
        {"query": "never-expose-this", "path": "."},
    )
    assert secret_search["results"] == []

    safe_search = await registry.execute(
        "workspace_search",
        {"query": "VISIBLE_MARKER", "path": "."},
    )
    assert [item["path"] for item in safe_search["results"]] == ["src.py"]

    summary = await registry.execute("project_summary", {})
    top_level_names = {item["name"] for item in summary["top_level"]}
    assert ".env" not in top_level_names
    assert "credentials.json" not in top_level_names
    assert ".ssh" not in top_level_names
    assert ".env.example" in top_level_names
    assert "src.py" in top_level_names
