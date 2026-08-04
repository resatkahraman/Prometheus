from __future__ import annotations

import hashlib
import io
import json
import math
import wave
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

import tools.pandora_voice_studio.server as server


REVISION = "bffb3df5a29440629464e5e839f4d214c8714c3d"
RUNTIME_REVISION = "e2d6902dd4c1301892935d0a0277325551e8060e"
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


def _build_pack(path: Path) -> Path:
    audio = _wav()
    digest = hashlib.sha256(audio).hexdigest()
    persona_hash = hashlib.sha256(b"persona").hexdigest()
    clips = {
        category: {
            "path": f"candidates/pandora-01/{category}.wav",
            "sha256": digest,
        }
        for category in CATEGORIES
    }
    manifest = {
        "model_id": "openbmb/VoxCPM2",
        "model_revision": REVISION,
        "persona_hash": persona_hash,
        "candidates": [{
            "candidate_id": "pandora-01",
            "seed": 42,
            "persona_hash": persona_hash,
            "model_revision": REVISION,
            "reference": {
                "path": "candidates/pandora-01/reference.wav",
                "sha256": digest,
                "transcript": "Merhaba, ben Pandora. Bugün birlikte çalışmaya hazırım.",
            },
            "clips": clips,
        }],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("candidates/pandora-01/reference.wav", audio)
        for clip in clips.values():
            archive.writestr(clip["path"], audio)
    return path


def _configure(monkeypatch, tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    project = tmp_path / "project"
    (project / "config").mkdir(parents=True)
    (project / "config" / "pandora_voice_models.json").write_text(
        json.dumps({
            "voice_design": {"model_id": "openbmb/VoxCPM2", "revision": REVISION},
            "production_runtime": {
                "model_id": "ResembleAI/chatterbox",
                "revision": RUNTIME_REVISION,
            },
        }),
        encoding="utf-8",
    )
    assets = tmp_path / "assets"
    monkeypatch.setattr(server, "_PROJECT_ROOT", project)
    monkeypatch.setattr(server, "VOICE_ASSET_ROOT", assets)
    monkeypatch.setattr(server, "CANDIDATES_DIR", assets / "candidates")
    monkeypatch.setattr(server, "MASTER_DIR", assets / "master")
    return TestClient(server.studio_app), {"X-Pandora-Studio-Token": server._STUDIO_TOKEN}


def test_studio_requires_token(monkeypatch, tmp_path: Path) -> None:
    client, _ = _configure(monkeypatch, tmp_path)
    assert client.get("/api/packs").status_code == 401


def test_studio_import_and_explicit_selection(monkeypatch, tmp_path: Path) -> None:
    client, headers = _configure(monkeypatch, tmp_path)
    pack_path = _build_pack(tmp_path / "candidates.zip")
    imported = client.post("/api/import", headers=headers, json={"zip_path": str(pack_path)})
    assert imported.status_code == 200
    pack_hash = imported.json()["pack_hash"]

    candidates = client.get(f"/api/packs/{pack_hash}/candidates", headers=headers)
    assert candidates.status_code == 200
    assert candidates.json()[0]["selectable"] is True

    wrong = client.post(
        "/api/select-pandora",
        headers=headers,
        json={
            "pack_hash": pack_hash,
            "candidate_id": "pandora-01",
            "confirmation": "yes",
            "accepted_categories": CATEGORIES,
        },
    )
    assert wrong.status_code == 400

    selected = client.post(
        "/api/select-pandora",
        headers=headers,
        json={
            "pack_hash": pack_hash,
            "candidate_id": "pandora-01",
            "confirmation": "SELECT PANDORA pandora-01",
            "accepted_categories": CATEGORIES,
        },
    )
    assert selected.status_code == 200
    profile = server.MASTER_DIR / "pandora_voice_profile.json"
    assert profile.is_file()
    assert json.loads(profile.read_text(encoding="utf-8"))["approved_by_user"] is True


def test_studio_audio_uses_header_not_query_token(monkeypatch, tmp_path: Path) -> None:
    client, headers = _configure(monkeypatch, tmp_path)
    imported = client.post(
        "/api/import",
        headers=headers,
        json={"zip_path": str(_build_pack(tmp_path / "candidates.zip"))},
    ).json()
    url = f"/api/packs/{imported['pack_hash']}/candidates/pandora-01/audio/01_greeting"
    assert client.get(url).status_code == 401
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
