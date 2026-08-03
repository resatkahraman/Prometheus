from pathlib import Path

import pytest

from app.tools.base import ToolError
from app.workspace.policy import WorkspacePolicy


def make_policy(tmp_path: Path) -> WorkspacePolicy:
    return WorkspacePolicy(
        root=tmp_path,
        max_file_bytes=100_000,
        max_search_results=20,
    )


def test_workspace_blocks_parent_escape(tmp_path):
    policy = make_policy(tmp_path)
    with pytest.raises(ToolError):
        policy.resolve("../outside.txt")


def test_workspace_blocks_absolute_path(tmp_path):
    policy = make_policy(tmp_path)
    with pytest.raises(ToolError):
        policy.resolve(str((tmp_path / "file.txt").resolve()))


def test_workspace_blocks_env_write(tmp_path):
    policy = make_policy(tmp_path)
    with pytest.raises(ToolError):
        policy.resolve(".env", for_write=True)


def test_workspace_blocks_temp_and_benchmark_artifacts(tmp_path):
    policy = make_policy(tmp_path)
    with pytest.raises(ToolError):
        policy.resolve(".test-tmp-active/file.txt")
    with pytest.raises(ToolError):
        policy.resolve("benchmark-run/data.json")

    # Verify iter_files ignores temp & benchmark directories
    (tmp_path / ".test-tmp-foo").mkdir()
    (tmp_path / ".test-tmp-foo" / "temp.txt").write_text("temp", encoding="utf-8")
    (tmp_path / "valid.txt").write_text("valid", encoding="utf-8")

    files = [str(p.name) for p in policy.iter_files(tmp_path)]
    assert "temp.txt" not in files
    assert "valid.txt" in files


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        ".env.production",
        "nested/.env.test",
        "credentials.json",
        "service-account.json",
        "service_account.json",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "private.pem",
        "private.KEY",
        "certificate.p12",
        "certificate.PFX",
        "id_rsa",
        "id_ed25519",
        ".ssh/config",
        ".aws/credentials",
        ".gcp/application_default_credentials.json",
        ".azure/accessTokens.json",
    ],
)
def test_workspace_blocks_sensitive_paths_for_read_and_write(tmp_path, path):
    policy = make_policy(tmp_path)

    with pytest.raises(ToolError, match="Hassas"):
        policy.resolve(path)
    with pytest.raises(ToolError, match="Hassas"):
        policy.resolve(path, for_write=True)


@pytest.mark.parametrize(
    "path",
    [
        ".env.example",
        ".gitignore",
        ".github/workflows/test.yml",
        "src/config.py",
    ],
)
def test_workspace_allows_non_secret_dotfiles_and_source_paths(tmp_path, path):
    policy = make_policy(tmp_path)
    assert policy.resolve(path) == (tmp_path / path).resolve()
    assert policy.resolve(path, for_write=True) == (tmp_path / path).resolve()


def test_workspace_normalizes_sensitive_paths_before_checking(tmp_path):
    policy = make_policy(tmp_path)
    (tmp_path / "nested").mkdir()

    for path in ("./.env", "nested/../.env", "nested/../.env.local"):
        with pytest.raises(ToolError, match="Hassas"):
            policy.resolve(path)


def test_workspace_blocks_symlink_to_sensitive_target(tmp_path):
    policy = make_policy(tmp_path)
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")
    alias = tmp_path / "safe-looking.txt"
    try:
        alias.symlink_to(tmp_path / ".env")
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is not supported in this environment")

    with pytest.raises(ToolError, match="Hassas"):
        policy.resolve("safe-looking.txt", must_exist=True)


def test_iter_files_omits_sensitive_files_and_directories(tmp_path):
    policy = make_policy(tmp_path)
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")
    (tmp_path / "credentials.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".ssh").mkdir()
    (tmp_path / ".ssh" / "config").write_text("Host *", encoding="utf-8")
    (tmp_path / ".env.example").write_text("KEY=", encoding="utf-8")
    (tmp_path / "src.py").write_text("print('ok')", encoding="utf-8")

    paths = {policy.relative(path) for path in policy.iter_files(policy.root)}

    assert ".env" not in paths
    assert "credentials.json" not in paths
    assert ".ssh/config" not in paths
    assert ".env.example" in paths
    assert "src.py" in paths
