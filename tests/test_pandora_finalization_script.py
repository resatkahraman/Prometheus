from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


def test_main_venv_does_not_require_chatterbox() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", "import chatterbox"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    assert proc.returncode != 0
    assert "No module named 'chatterbox'" in proc.stderr or "ModuleNotFoundError" in proc.stderr


def test_finalization_script_has_exact_orchestration_sequence() -> None:
    root = Path(__file__).parents[1]
    script_path = root / "scripts" / "finalize_pandora_tts.ps1"
    assert script_path.is_file()

    content = script_path.read_text(encoding="utf-8")

    apply_idx = content.find("-Apply")
    download_idx = content.find("download_pandora_model.py")
    verify_idx = content.find("-VerifyOnly")
    profile_idx = content.find("pandora-11")
    benchmark_idx = content.find("benchmark_pandora_tts.py")
    parse_idx = content.find("runtime_benchmark.json")

    assert apply_idx != -1
    assert download_idx != -1
    assert verify_idx != -1
    assert profile_idx != -1
    assert benchmark_idx != -1
    assert parse_idx != -1

    assert apply_idx < download_idx < verify_idx < profile_idx < benchmark_idx < parse_idx
    assert content.count("-VerifyOnly") == 1

    assert '"SUCCESS"' in content
    assert "exit 0" in content
    assert "RUNTIME_MEMORY_BLOCKED" in content
    assert "QUALITY_REJECTED" in content
    assert "MODEL_DOWNLOAD_FAILED" in content
    assert "ENVIRONMENT_INVALID" in content

    assert "C:\\Users\\Reşat" not in content
    assert "api_key" not in content.lower()
    assert "hf_token" not in content.lower()


def test_finalization_script_powershell_syntax_valid() -> None:
    root = Path(__file__).parents[1]
    script_path = root / "scripts" / "finalize_pandora_tts.ps1"

    ps_code = f"""
    $err = $null
    [System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$err)
    if ($err.Count -gt 0) {{
        $err | ForEach-Object {{ Write-Error $_.Message }}
        exit 1
    }}
    """
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps_code],
        capture_output=True,
        text=True,
        errors="replace",
    )
    assert proc.returncode == 0, f"PowerShell syntax error: {proc.stderr}"
