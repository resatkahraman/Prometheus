import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_runtime_uses_bundled_sidecar_and_app_data(tmp_path):
    source = (ROOT / "desktop/src-tauri/src/core_runtime.rs").read_text(encoding="utf-8")
    assert 'SIDECAR_NAME: &str = "prometheus-core.exe"' in source
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
    assert package["version"] == "0.1.6"
    assert "build:core-sidecar" in package["scripts"]
    assert tauri["version"] == "0.1.6"
    assert tauri["build"]["beforeBuildCommand"].startswith("npm.cmd run build:core-sidecar")
    assert tauri["bundle"]["externalBin"] == ["binaries/prometheus-core"]


def test_sidecar_build_and_smoke_tools_are_present():
    build = (ROOT / "scripts/build_desktop_core_sidecar.py").read_text(encoding="utf-8")
    smoke = (ROOT / "scripts/smoke_desktop_core_sidecar.py").read_text(encoding="utf-8")
    collision = (ROOT / "scripts/smoke_desktop_core_port_collision.py").read_text(encoding="utf-8")
    assert "PyInstaller" in build
    assert "prometheus-core-x86_64-pc-windows-msvc" in build
    assert "127.0.0.1:18765/v1/health" in smoke
    assert "creationflags=0x08000000" in smoke
    assert "8765" in collision and "18766" in collision


def test_frozen_entrypoint_configures_logging_without_tty(monkeypatch):
    import uvicorn

    import app.desktop_server as server

    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    server._STDIO_SINKS.clear()
    server.ensure_noninteractive_stdio()
    assert sys.stdout is not None and not sys.stdout.isatty()
    assert sys.stderr is not None and not sys.stderr.isatty()
    config = uvicorn.Config("app.main:app", use_colors=False)
    assert config.use_colors is False
    config.load()
    for sink in server._STDIO_SINKS:
        sink.close()
    server._STDIO_SINKS.clear()


def test_no_console_entrypoint_contract_remains_intact():
    entrypoint = (ROOT / "app/desktop_server.py").read_text(encoding="utf-8")
    rust_main = (ROOT / "desktop/src-tauri/src/main.rs").read_text(encoding="utf-8")
    assert "use_colors=False" in entrypoint
    assert "windows_subsystem = \"windows\"" in rust_main


def test_runtime_port_negotiation_contract():
    runtime = (ROOT / "desktop/src-tauri/src/core_runtime.rs").read_text(encoding="utf-8")
    transport = (ROOT / "desktop/src-tauri/src/core_transport.rs").read_text(encoding="utf-8")
    server = (ROOT / "app/desktop_server.py").read_text(encoding="utf-8")
    assert "TcpListener::bind((core_transport::CORE_HOST, 0))" in runtime
    assert "MAX_START_ATTEMPTS: usize = 3" in runtime
    assert '.env("PROMETHEUS_CORE_PORT", selected_port.to_string())' in runtime
    assert "set_runtime_port(selected_port)" in runtime
    assert "clear_runtime_port()" in runtime
    assert "AtomicU16" in transport
    assert 'CORE_PORT_ENV = "PROMETHEUS_CORE_PORT"' in server
    assert '127.0.0.1' in server
