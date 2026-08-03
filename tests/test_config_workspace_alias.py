from pathlib import Path

from app.core.config import Settings


def test_prometheus_workspace_root_environment_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("PROMETHEUS_WORKSPACE_ROOT", str(tmp_path))
    settings = Settings(_env_file=None)
    assert settings.workspace_root == Path(tmp_path)


def test_legacy_adam_workspace_root_environment_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("ADAM_WORKSPACE_ROOT", str(tmp_path))
    settings = Settings(_env_file=None)
    assert settings.workspace_root == Path(tmp_path)
