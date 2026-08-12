from __future__ import annotations

import json
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = ROOT / "desktop"


def test_release_identity_and_version_are_consistent() -> None:
    package = json.loads((DESKTOP / "package.json").read_text(encoding="utf-8"))
    tauri = json.loads((DESKTOP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    cargo = tomllib.loads((DESKTOP / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8"))
    assert package["version"] == tauri["version"] == cargo["package"]["version"] == "0.1.3"
    assert tauri["productName"] == "Prometheus"
    assert tauri["identifier"] == "com.resatkahraman.prometheus"


def test_release_bundle_is_explicitly_nsis_and_uses_prometheus_icons() -> None:
    tauri = json.loads((DESKTOP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    bundle = tauri["bundle"]
    assert bundle["targets"] == ["nsis"]
    assert "icons/icon.ico" in bundle["icon"]
    assert (DESKTOP / "src-tauri" / "icons" / "icon.ico").is_file()
    assert bundle["windows"]["nsis"]["installMode"] == "currentUser"


def test_release_security_has_no_updater_or_development_bypass() -> None:
    tauri = json.loads((DESKTOP / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    serialized = json.dumps(tauri).casefold()
    assert "dangerousdisableassetcspmodification" not in serialized
    assert "dangerousdisablecspmodification" not in serialized
    assert "updater" not in tauri
    assert "unsafe-eval" not in tauri["app"]["security"]["csp"]
    assert "http://*" not in tauri["app"]["security"]["csp"]


def test_canonical_model_stack_and_release_diagnostics_are_preserved() -> None:
    config = (ROOT / "app" / "core" / "config.py").read_text(encoding="utf-8")
    native = (DESKTOP / "src-tauri" / "src" / "native_os.rs").read_text(encoding="utf-8")
    for model in ("gemma4:e4b-it-qat", "embeddinggemma:300m-qat-q4_0", "ministral-3:3b"):
        assert model in config
    assert "development_workspace_python" in native
    assert "not_configured" in native
    assert "ollama pull" not in native.casefold()
