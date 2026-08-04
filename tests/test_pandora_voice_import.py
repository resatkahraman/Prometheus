from __future__ import annotations

import hashlib
import io
import json
import math
import wave
import zipfile
from pathlib import Path

import pytest

from tools.pandora_voice_studio.import_pack import CandidatePackError, import_candidate_pack


REVISION = "bffb3df5a29440629464e5e839f4d214c8714c3d"
PERSONA_HASH = hashlib.sha256(b"persona").hexdigest()
CATEGORIES = [
    "01_greeting",
    "02_weather",
    "03_news",
    "04_technical_success",
    "05_security_warning",
    "06_numbers_dates",
    "07_mixed_turkish_english",
    "08_long_form",
]


def _wav(seconds: float = 7.0, sample_rate: int = 16000) -> bytes:
    output = io.BytesIO()
    frames = bytearray()
    for index in range(int(seconds * sample_rate)):
        sample = int(math.sin(index * 2 * math.pi * 220 / sample_rate) * 9000)
        frames.extend(sample.to_bytes(2, "little", signed=True))
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(bytes(frames))
    return output.getvalue()


def _pack(path: Path, *, bad_reference_hash: bool = False, traversal: bool = False) -> Path:
    audio = _wav()
    audio_hash = hashlib.sha256(audio).hexdigest()
    ref_path = "../escape.wav" if traversal else "candidates/pandora-01/reference.wav"
    clips = {}
    for category in CATEGORIES:
        clip_path = f"candidates/pandora-01/{category}.wav"
        clips[category] = {"path": clip_path, "sha256": audio_hash}
    manifest = {
        "model_id": "openbmb/VoxCPM2",
        "model_revision": REVISION,
        "persona_hash": PERSONA_HASH,
        "candidates": [{
            "candidate_id": "pandora-01",
            "seed": 42,
            "persona_hash": PERSONA_HASH,
            "model_revision": REVISION,
            "reference": {
                "path": ref_path,
                "sha256": "0" * 64 if bad_reference_hash else audio_hash,
                "transcript": "Merhaba, ben Pandora. Bugün birlikte çalışmaya hazırım.",
            },
            "clips": clips,
        }],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        if not traversal:
            archive.writestr(ref_path, audio)
        for values in clips.values():
            archive.writestr(values["path"], audio)
    return path


def test_secure_import_validates_all_hashes(tmp_path: Path) -> None:
    pack = import_candidate_pack(_pack(tmp_path / "valid.zip"), tmp_path / "target")
    assert pack.model_revision == REVISION
    assert len(pack.candidates) == 1
    candidate = pack.candidates[0]
    assert set(candidate.clip_sha256) == set(CATEGORIES)


def test_import_rejects_reference_hash_mismatch(tmp_path: Path) -> None:
    with pytest.raises(CandidatePackError, match="SHA-256 mismatch"):
        import_candidate_pack(_pack(tmp_path / "bad.zip", bad_reference_hash=True), tmp_path / "target")


def test_import_rejects_manifest_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(CandidatePackError, match="Unsafe"):
        import_candidate_pack(_pack(tmp_path / "traversal.zip", traversal=True), tmp_path / "target")


def test_import_rejects_zip_member_traversal(tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../evil.txt", "bad")
    with pytest.raises(CandidatePackError, match="Unsafe"):
        import_candidate_pack(path, tmp_path / "target")
