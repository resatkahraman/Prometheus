from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from tools.pandora_voice_studio.import_pack import _load_manifest
from tools.pandora_voice_studio.models import PackManifest


def load_pack_manifest(pack_dir: str | Path) -> PackManifest:
    pack_dir = Path(pack_dir)
    manifest = _load_manifest(pack_dir / "manifest.json", pack_dir.name)
    state_path = pack_dir / "candidate_state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            state = {}
        if isinstance(state, dict):
            for candidate in manifest.candidates:
                values = state.get(candidate.candidate_id)
                if isinstance(values, dict):
                    candidate.favorite = values.get("favorite") is True
                    candidate.rejected = values.get("rejected") is True
                    notes = values.get("notes")
                    candidate.notes = str(notes)[:2000] if notes is not None else ""
    return manifest


def save_candidate_state(
    pack_dir: str | Path,
    candidate_id: str,
    *,
    favorite: bool | None = None,
    rejected: bool | None = None,
    notes: str | None = None,
) -> None:
    pack_dir = Path(pack_dir)
    manifest = load_pack_manifest(pack_dir)
    if candidate_id not in {candidate.candidate_id for candidate in manifest.candidates}:
        raise KeyError(f"Candidate not found: {candidate_id}")

    state_path = pack_dir / "candidate_state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    current = state.get(candidate_id)
    if not isinstance(current, dict):
        current = {}
    if favorite is not None:
        current["favorite"] = bool(favorite)
    if rejected is not None:
        current["rejected"] = bool(rejected)
    if notes is not None:
        current["notes"] = str(notes)[:2000]
    state[candidate_id] = current

    fd, temp_name = tempfile.mkstemp(prefix=".candidate-state.", suffix=".json", dir=pack_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, state_path)
    finally:
        Path(temp_name).unlink(missing_ok=True)
