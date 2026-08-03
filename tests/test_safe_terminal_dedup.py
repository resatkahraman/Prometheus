import os
from pathlib import Path

from app.core.config import Settings
from app.tools.registry import build_default_tool_registry


def test_pytest_extra_q_is_not_duplicated(tmp_path: Path):
    settings = Settings(workspace_root=tmp_path)
    registry = build_default_tool_registry(settings=settings)
    tool = registry.get("safe_terminal")
    command = tool._command(
        {"preset": "pytest", "extra_args": ["-q", "-q"]}
    )
    assert command.count("-q") == 1
    assert command[command.index("-c") + 1] == os.devnull
    assert "--rootdir=." in command
    assert "--confcutdir=." in command


def test_pytest_uses_workspace_config_instead_of_parent(
    tmp_path: Path,
):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'testpaths = ["checks"]\n',
        encoding="utf-8",
    )
    settings = Settings(workspace_root=tmp_path)
    tool = build_default_tool_registry(
        settings=settings
    ).get("safe_terminal")

    command = tool._command(
        {"preset": "pytest", "extra_args": []}
    )

    assert command[command.index("-c") + 1] == "pyproject.toml"
