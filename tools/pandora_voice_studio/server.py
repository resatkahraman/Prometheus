from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from tools.pandora_voice_studio.audio_metrics import analyze_wav
from tools.pandora_voice_studio.import_pack import CandidatePackError, SAFE_ID, import_candidate_pack
from tools.pandora_voice_studio.manifest import load_pack_manifest, save_candidate_state
from tools.pandora_voice_studio.reference_builder import build_master_reference
from tools.pandora_voice_studio.studio_ui import render_studio_ui_html


_PROJECT_ROOT = Path(
    os.environ.get("PANDORA_PROJECT_ROOT") or Path(__file__).resolve().parents[2]
).resolve()
_LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / ".local" / "share"))
VOICE_ASSET_ROOT = Path(
    os.environ.get("PANDORA_VOICE_ASSET_ROOT")
    or (_LOCALAPPDATA / "Prometheus" / "pandora_voice")
).resolve()
CANDIDATES_DIR = VOICE_ASSET_ROOT / "candidates"
MASTER_DIR = VOICE_ASSET_ROOT / "master"
_STUDIO_TOKEN = secrets.token_urlsafe(32)
_REQUIRED_CATEGORIES = {
    "01_greeting",
    "02_weather",
    "03_news",
    "04_technical_success",
    "05_security_warning",
    "06_numbers_dates",
    "07_mixed_turkish_english",
    "08_long_form",
}


studio_app = FastAPI(
    title="Pandora Voice Studio",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


class ImportRequest(BaseModel):
    zip_path: str = Field(min_length=1, max_length=4096)


class CandidateStateUpdate(BaseModel):
    favorite: bool | None = None
    rejected: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)


class SelectCandidateRequest(BaseModel):
    pack_hash: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    confirmation: str = Field(min_length=1, max_length=128)
    accepted_categories: list[str] = Field(min_length=8, max_length=8)


def _require_token(value: str | None) -> None:
    if not value or not secrets.compare_digest(value, _STUDIO_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _safe_id(value: str, label: str) -> str:
    if not SAFE_ID.fullmatch(value):
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return value


def _pack_dir(pack_hash: str) -> Path:
    path = CANDIDATES_DIR / _safe_id(pack_hash, "pack hash")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="Pack not found")
    return path


def _candidate(pack_hash: str, candidate_id: str):
    pack_dir = _pack_dir(pack_hash)
    manifest = load_pack_manifest(pack_dir)
    candidate_id = _safe_id(candidate_id, "candidate id")
    candidate = next((item for item in manifest.candidates if item.candidate_id == candidate_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return pack_dir, manifest, candidate


@studio_app.get("/", response_class=HTMLResponse)
async def studio_ui(token: str = Query(default="")) -> str:
    _require_token(token)
    return render_studio_ui_html(_STUDIO_TOKEN)


@studio_app.post("/api/import")
async def import_pack(
    request: ImportRequest,
    x_pandora_studio_token: str | None = Header(default=None),
) -> dict:
    _require_token(x_pandora_studio_token)
    try:
        pack = import_candidate_pack(request.zip_path, CANDIDATES_DIR)
    except (OSError, CandidatePackError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "imported", "pack_hash": pack.pack_hash, "candidate_count": len(pack.candidates)}


@studio_app.get("/api/packs")
async def list_packs(x_pandora_studio_token: str | None = Header(default=None)) -> list[dict]:
    _require_token(x_pandora_studio_token)
    output: list[dict] = []
    if not CANDIDATES_DIR.exists():
        return output
    for directory in sorted(CANDIDATES_DIR.iterdir()):
        if not directory.is_dir():
            continue
        try:
            manifest = load_pack_manifest(directory)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        output.append(
            {
                "pack_hash": manifest.pack_hash,
                "model_id": manifest.model_id,
                "candidate_count": len(manifest.candidates),
                "import_timestamp": manifest.import_timestamp,
            }
        )
    return output


@studio_app.get("/api/packs/{pack_hash}/candidates")
async def list_candidates(
    pack_hash: str,
    x_pandora_studio_token: str | None = Header(default=None),
) -> list[dict]:
    _require_token(x_pandora_studio_token)
    pack_dir = _pack_dir(pack_hash)
    manifest = load_pack_manifest(pack_dir)
    output: list[dict] = []
    for candidate in manifest.candidates:
        reference = pack_dir / candidate.reference_path
        try:
            metrics = analyze_wav(reference)
            selectable = metrics.selectable and 6.0 <= metrics.duration_seconds <= 12.0
            metrics_dict = metrics.__dict__
        except (OSError, ValueError):
            selectable = False
            metrics_dict = {"error": "Reference audio could not be analyzed"}
        output.append(
            {
                "candidate_id": candidate.candidate_id,
                "seed": candidate.seed,
                "favorite": candidate.favorite,
                "rejected": candidate.rejected,
                "notes": candidate.notes,
                "selectable": selectable and not candidate.rejected,
                "metrics": metrics_dict,
                "categories": sorted(candidate.clips),
            }
        )
    return output


@studio_app.get("/api/packs/{pack_hash}/candidates/{candidate_id}/audio/{category}")
async def candidate_audio(
    pack_hash: str,
    candidate_id: str,
    category: str,
    x_pandora_studio_token: str | None = Header(default=None),
) -> FileResponse:
    _require_token(x_pandora_studio_token)
    pack_dir, _, candidate = _candidate(pack_hash, candidate_id)
    relative = candidate.reference_path if category == "reference" else candidate.clips.get(category, "")
    if not relative:
        raise HTTPException(status_code=404, detail="Audio category not found")
    path = (pack_dir / relative).resolve()
    try:
        path.relative_to(pack_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unsafe audio path") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/wav", filename=f"{candidate_id}-{category}.wav")


@studio_app.put("/api/packs/{pack_hash}/candidates/{candidate_id}")
async def update_candidate(
    pack_hash: str,
    candidate_id: str,
    update: CandidateStateUpdate,
    x_pandora_studio_token: str | None = Header(default=None),
) -> dict:
    _require_token(x_pandora_studio_token)
    pack_dir, _, candidate = _candidate(pack_hash, candidate_id)
    save_candidate_state(
        pack_dir,
        candidate.candidate_id,
        favorite=update.favorite,
        rejected=update.rejected,
        notes=update.notes,
    )
    return {"status": "updated"}


@studio_app.post("/api/select-pandora")
async def select_as_pandora(
    request: SelectCandidateRequest,
    x_pandora_studio_token: str | None = Header(default=None),
) -> dict:
    _require_token(x_pandora_studio_token)
    pack_dir, manifest, candidate = _candidate(request.pack_hash, request.candidate_id)
    if candidate.rejected:
        raise HTTPException(status_code=400, detail="Rejected candidate cannot be selected")
    expected_confirmation = f"SELECT PANDORA {candidate.candidate_id}"
    if not secrets.compare_digest(request.confirmation, expected_confirmation):
        raise HTTPException(status_code=400, detail=f"Confirmation must be: {expected_confirmation}")
    if set(request.accepted_categories) != _REQUIRED_CATEGORIES:
        raise HTTPException(status_code=400, detail="All eight quality categories must be accepted")
    metrics = analyze_wav(pack_dir / candidate.reference_path)
    if not metrics.selectable or not (6.0 <= metrics.duration_seconds <= 12.0):
        raise HTTPException(status_code=400, detail="Reference audio failed automatic quality gates")

    config_path = _PROJECT_ROOT / "config" / "pandora_voice_models.json"
    if not config_path.is_file():
        raise HTTPException(status_code=500, detail="Pandora model config not found")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        design = config["voice_design"]
        runtime = config["production_runtime"]
        if manifest.model_id != design["model_id"] or manifest.model_revision != design["revision"]:
            raise ValueError("Candidate pack does not match pinned voice-design model")
        profile = build_master_reference(
            pack_dir=pack_dir,
            candidate=candidate,
            master_dir=MASTER_DIR,
            design_model=design["model_id"],
            design_revision=design["revision"],
            runtime_model=runtime["model_id"],
            runtime_revision=runtime["revision"],
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "selected",
        "voice_name": "Pandora",
        "candidate_id": candidate.candidate_id,
        "reference_sha256": profile["reference_sha256"],
    }


@studio_app.get("/api/master-profile")
async def master_profile(x_pandora_studio_token: str | None = Header(default=None)) -> dict:
    _require_token(x_pandora_studio_token)
    path = MASTER_DIR / "pandora_voice_profile.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No master profile")
    return json.loads(path.read_text(encoding="utf-8"))


def run_studio(host: str = "127.0.0.1", port: int = 9724) -> None:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("Pandora Voice Studio may only bind to loopback")
    import uvicorn

    print(f"Pandora Voice Studio: http://{host}:{port}/?token={_STUDIO_TOKEN}")
    uvicorn.run(studio_app, host=host, port=port, log_level="warning", access_log=False)


if __name__ == "__main__":
    run_studio()
