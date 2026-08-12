from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"
TAURI_SRC = DESKTOP / "src-tauri" / "src"


def test_titlebar_drag_region_preserves_controls() -> None:
    source = (DESKTOP / "src" / "components" / "window" / "TitleBar.tsx").read_text(encoding="utf-8")
    assert "titlebarDragSurface" in source
    assert "data-tauri-drag-region" in source
    assert "className=\"windowButtons\"" in source
    assert "onClick={() => w.minimize()}" in source


def test_release_gui_and_version_contract() -> None:
    package = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
    tauri = json.loads((DESKTOP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    cargo = (DESKTOP / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
    main = (TAURI_SRC / "main.rs").read_text(encoding="utf-8")
    assert package["version"] == tauri["version"] == "0.1.1"
    assert 'version="0.1.1"' in cargo
    assert 'windows_subsystem = "windows"' in main


def test_core_launcher_hides_windows_console_without_authority_widening() -> None:
    source = (TAURI_SRC / "core_runtime.rs").read_text(encoding="utf-8")
    assert "creation_flags(0x0800_0000)" in source
    assert "app.desktop_server" in source
    assert "cmd.exe" not in source.casefold()
    assert "powershell" not in source.casefold()
    assert "PATH" not in source


def test_desktop_submit_keeps_csrf_and_canonical_transport() -> None:
    source = (TAURI_SRC / "core_transport.rs").read_text(encoding="utf-8")
    assert 'CSRF_HEADER_NAME: &str = "X-Prometheus-CSRF"' in source
    assert 'CSRF_HEADER_VALUE: &str = "1"' in source
    assert 'post(endpoint("/v1/desktop/command"))' in source
    assert "auth_header" in source
    config = (ROOT / "app" / "core" / "config.py").read_text(encoding="utf-8")
    for model in ("gemma4:e4b-it-qat", "embeddinggemma:300m-qat-q4_0", "ministral-3:3b"):
        assert model in config
