from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.main import app, workspace_files, workspace_preview


@pytest.mark.asyncio
async def test_workspace_http_routes_hide_sensitive_files(tmp_path) -> None:
    (tmp_path / ".env").write_text(
        "SECRET=never-return",
        encoding="utf-8",
    )
    (tmp_path / "credentials.json").write_text(
        '{"token":"never-return"}',
        encoding="utf-8",
    )
    (tmp_path / "visible.txt").write_text(
        "safe",
        encoding="utf-8",
    )

    previous_settings = getattr(app.state, "settings", None)
    app.state.settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
    )

    try:
        files = await workspace_files()
        paths = {item["path"] for item in files}

        assert ".env" not in paths
        assert "credentials.json" not in paths
        assert "visible.txt" in paths

        for path in (".env", "credentials.json"):
            with pytest.raises(HTTPException) as captured:
                await workspace_preview(path)

            assert captured.value.status_code == 404
            assert "Hassas" in str(captured.value.detail)
    finally:
        if previous_settings is None:
            delattr(app.state, "settings")
        else:
            app.state.settings = previous_settings
