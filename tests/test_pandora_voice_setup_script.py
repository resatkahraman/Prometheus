from __future__ import annotations

from pathlib import Path


def test_setup_script_is_isolated_and_dry_run_by_default() -> None:
    root = Path(__file__).parents[1]
    source = (root / "scripts" / "setup_pandora_tts.ps1").read_text(encoding="utf-8")
    assert r'venvs\pandora-tts' in source
    assert "if (-not $Apply)" in source
    assert "chatterbox-tts==$ChatterboxVersion" in source
    assert "$ChatterboxVersion = \"0.1.7\"" in source
    assert "$TorchVersion = \"2.6.0\"" in source
    assert "C:\\Users\\Reşat" not in source
    assert ".venv\\Scripts" not in source


def test_setup_verifier_checks_multilingual_v3_and_turkish() -> None:
    root = Path(__file__).parents[1]
    source = (root / "scripts" / "setup_pandora_tts.ps1").read_text(encoding="utf-8")
    assert "ChatterboxMultilingualTTS" in source
    assert "get_supported_languages" in source
    assert '"tr"' in source


def test_colab_notebook_has_no_drive_or_api_key_dependency() -> None:
    root = Path(__file__).parents[1]
    notebook = (
        root
        / "tools"
        / "pandora_voice_studio"
        / "PANDORA_VOICE_DESIGN_COLAB.ipynb"
    ).read_text(encoding="utf-8")
    assert "openbmb/VoxCPM2" in notebook
    assert "bffb3df5a29440629464e5e839f4d214c8714c3d" in notebook
    assert "drive.mount" not in notebook
    assert "api_key" not in notebook.lower()
    assert "pandora_voice_candidates.zip" in notebook
