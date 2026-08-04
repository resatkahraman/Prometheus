from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from tools.pandora_voice_studio.audio_metrics import analyze_wav
from tools.pandora_voice_studio.models import CandidateManifest


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_master_reference(
    *,
    pack_dir: str | Path,
    candidate: CandidateManifest,
    master_dir: str | Path,
    design_model: str,
    design_revision: str,
    runtime_model: str,
    runtime_revision: str,
) -> dict:
    pack_dir = Path(pack_dir).resolve()
    master_dir = Path(master_dir).resolve()
    source = (pack_dir / candidate.reference_path).resolve()
    try:
        source.relative_to(pack_dir)
    except ValueError as exc:
        raise ValueError("Reference path escapes candidate pack") from exc
    if not source.is_file():
        raise FileNotFoundError(f"Reference WAV missing: {candidate.reference_path}")

    actual_sha = _sha256_file(source)
    if actual_sha != candidate.reference_sha256:
        raise ValueError("Reference SHA changed after import")

    metrics = analyze_wav(source)
    # Official Chatterbox V3 conditioning consumes about 6 seconds for the
    # encoder and at most 10 seconds for the decoder. Keep the master reference
    # compact and exact instead of pretending a 30-second clip is used fully.
    if not (6.0 <= metrics.duration_seconds <= 12.0):
        raise ValueError(
            f"Reference duration must be 6–12 seconds; got {metrics.duration_seconds:.2f}s"
        )
    if not metrics.selectable:
        raise ValueError(f"Reference audio failed quality gates: {metrics}")

    transcript = candidate.reference_transcript.strip()
    if not transcript:
        raise ValueError("Exact reference transcript is required")

    parent = master_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pandora-master.", dir=parent))
    backup = master_dir.with_name(master_dir.name + ".previous")
    try:
        shutil.copyfile(source, staging / "pandora_reference.wav")
        (staging / "pandora_reference.txt").write_text(transcript + "\n", encoding="utf-8")

        profile = {
            "schema_version": 1,
            "voice_name": "Pandora",
            "candidate_id": candidate.candidate_id,
            "design_model": design_model,
            "design_revision": design_revision,
            "runtime_model": runtime_model,
            "runtime_revision": runtime_revision,
            "language": "tr",
            "reference_sha256": actual_sha,
            "reference_transcript_sha256": hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
            "reference_duration_seconds": metrics.duration_seconds,
            "reference_sample_rate": metrics.sample_rate,
            "approved_by_user": True,
            "selected_at": datetime.now(timezone.utc).isoformat(),
        }
        (staging / "pandora_voice_profile.json").write_text(
            json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        selection = {
            "candidate_id": candidate.candidate_id,
            "pack_hash": pack_dir.name,
            "reference_relative_path": candidate.reference_path,
            "reference_sha256": candidate.reference_sha256,
            "clip_sha256": candidate.clip_sha256,
            "profile": profile,
        }
        (staging / "selection_manifest.json").write_text(
            json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        if backup.exists():
            shutil.rmtree(backup)
        if master_dir.exists():
            os.replace(master_dir, backup)
        os.replace(staging, master_dir)
        if backup.exists():
            shutil.rmtree(backup)
        return profile
    except Exception:
        if not master_dir.exists() and backup.exists():
            os.replace(backup, master_dir)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
