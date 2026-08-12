import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_runtime_uses_bundled_sidecar_and_app_data(tmp_path):
    source = (ROOT / "desktop/src-tauri/src/core_runtime.rs").read_text(encoding="utf-8")
    assert 'SIDECAR_NAME: &str = "prometheus-core-x86_64-pc-windows-msvc.exe"' in source
    assert "resource_dir()" in source
    assert "app_data_dir()" in source
    assert "if cfg!(debug_assertions)" in source
    assert "Command::new(executable)" in source


def test_release_runtime_does_not_use_generic_process_or_shell_authority():
    source = (ROOT / "desktop/src-tauri/src/core_runtime.rs").read_text(encoding="utf-8")
    assert "powershell" not in source.lower()
    assert "cmd.exe" not in source.lower()
    assert "shell=True" not in source
    assert "Command::new(user" not in source


def test_sidecar_packaging_contract_and_version():
    package = json.loads((ROOT / "desktop/package.json").read_text(encoding="utf-8"))
    tauri = json.loads((ROOT / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    assert package["version"] == "0.1.3"
    assert "build:core-sidecar" in package["scripts"]
    assert tauri["version"] == "0.1.3"
    assert tauri["build"]["beforeBuildCommand"].startswith("npm.cmd run build:core-sidecar")
    assert tauri["bundle"]["externalBin"] == ["binaries/prometheus-core"]


def test_sidecar_build_and_smoke_tools_are_present():
    build = (ROOT / "scripts/build_desktop_core_sidecar.py").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/smoke_desktop_core_sidecar.py").read_text(encoding="utf-8")
    assert "PyInstaller" in build
    assert "prometheus-core-x86_64-pc-windows-msvc" in build
    assert "127.0.0.1:18765/v1/health" in smoke
    assert "creationflags=0x08000000" in smoke
