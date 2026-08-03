from __future__ import annotations

from app.supervisor.service import SupervisorService
from app.workspace.policy import WorkspacePolicy


def test_supervisor_raw_context_uses_sensitive_file_policy(tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "SECRET=never-read",
        encoding="utf-8",
    )
    (tmp_path / "credentials.json").write_text(
        '{"token":"never-read"}',
        encoding="utf-8",
    )
    (tmp_path / "src.py").write_text(
        "VISIBLE = True",
        encoding="utf-8",
    )

    service = SupervisorService.__new__(SupervisorService)
    service.workspace = WorkspacePolicy(
        root=tmp_path,
        max_file_bytes=100_000,
        max_search_results=20,
    )

    assert service._raw_workspace_text(".env") is None
    assert service._raw_workspace_text("credentials.json") is None
    assert service._raw_workspace_text("src.py") == "VISIBLE = True"
