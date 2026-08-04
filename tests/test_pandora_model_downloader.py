from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.download_pandora_model import REQUIRED, check_existing_snapshot


def test_required_files_list_matches_chatterbox_v3_multilingual() -> None:
    expected = [
        "ve.pt",
        "t3_mtl23ls_v3.safetensors",
        "s3gen.pt",
        "grapheme_mtl_merged_expanded_v1.json",
        "conds.pt",
        "Cangjie5_TC.json",
    ]
    assert REQUIRED == expected


def test_dry_run_mode_prints_plan_without_downloading(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({
            "production_runtime": {
                "model_id": "ResembleAI/chatterbox",
                "revision": "e2d6902dd4c1301892935d0a0277325551e8060e",
            }
        }),
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"

    cmd = [
        sys.executable,
        "scripts/download_pandora_model.py",
        "--config",
        str(config_path),
        "--cache-dir",
        str(cache_dir),
        "--dry-run",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["dry_run"] is True
    assert data["repo_id"] == "ResembleAI/chatterbox"
    assert data["revision"] == "e2d6902dd4c1301892935d0a0277325551e8060e"
    assert data["required_files"] == REQUIRED


def test_existing_snapshot_precheck_skips_download(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({
            "production_runtime": {
                "model_id": "ResembleAI/chatterbox",
                "revision": "e2d6902dd4c1301892935d0a0277325551e8060e",
            }
        }),
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache" / "snapshots" / "sub"
    cache_dir.mkdir(parents=True)
    for fname in REQUIRED:
        (cache_dir / fname).write_text("dummy data", encoding="utf-8")

    assert check_existing_snapshot(tmp_path / "cache") is not None

    cmd = [
        sys.executable,
        "scripts/download_pandora_model.py",
        "--config",
        str(config_path),
        "--cache-dir",
        str(tmp_path / "cache"),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["status"] == "already_present"
    assert data["revision"] == "e2d6902dd4c1301892935d0a0277325551e8060e"


def test_rejects_floating_revision(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({
            "production_runtime": {
                "model_id": "ResembleAI/chatterbox",
                "revision": "main",
            }
        }),
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"

    cmd = [
        sys.executable,
        "scripts/download_pandora_model.py",
        "--config",
        str(config_path),
        "--cache-dir",
        str(cache_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 1
    assert "Pinned 40-character SHA zorunludur" in proc.stderr
