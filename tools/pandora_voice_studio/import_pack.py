from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from tools.pandora_voice_studio.models import CandidateManifest, PackManifest


MAX_FILES = 256
MAX_TOTAL_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_WAV_BYTES = 128 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9a-f]{40}$")
REQUIRED_CLIPS = {
    "01_greeting",
    "02_weather",
    "03_news",
    "04_technical_success",
    "05_security_warning",
    "06_numbers_dates",
    "07_mixed_turkish_english",
    "08_long_form",
}


class CandidatePackError(ValueError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_member_path(name: str) -> PurePosixPath:
    if "\\" in name or "\x00" in name or ":" in name:
        raise CandidatePackError(f"Unsafe ZIP member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise CandidatePackError(f"Unsafe ZIP member path: {name!r}")
    return path


def _validate_entry(entry: zipfile.ZipInfo) -> PurePosixPath:
    path = _safe_member_path(entry.filename)
    unix_type = (entry.external_attr >> 16) & 0xF000
    if unix_type == 0xA000:
        raise CandidatePackError(f"Symlink is not allowed: {entry.filename}")
    if entry.file_size < 0 or entry.compress_size < 0:
        raise CandidatePackError(f"Invalid ZIP size: {entry.filename}")
    if entry.filename == "manifest.json" and entry.file_size > MAX_MANIFEST_BYTES:
        raise CandidatePackError("manifest.json is too large")
    if entry.filename.lower().endswith(".wav") and entry.file_size > MAX_WAV_BYTES:
        raise CandidatePackError(f"WAV is too large: {entry.filename}")
    if entry.compress_size == 0 and entry.file_size > 0:
        raise CandidatePackError(f"Suspicious compressed entry: {entry.filename}")
    if entry.compress_size and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO:
        raise CandidatePackError(f"Compression ratio is too high: {entry.filename}")
    return path


def _validated_audio(root: Path, relative: str, expected_sha: str, label: str) -> Path:
    member = _safe_member_path(relative)
    if member.suffix.lower() != ".wav":
        raise CandidatePackError(f"{label}: only WAV files are accepted")
    path = root.joinpath(*member.parts).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise CandidatePackError(f"{label}: unsafe audio path") from exc
    if not path.is_file():
        raise CandidatePackError(f"{label}: missing audio file {relative}")
    actual = _sha256_file(path)
    if actual != expected_sha:
        raise CandidatePackError(f"{label}: SHA-256 mismatch")
    return path


def _parse_clip(raw: object, candidate_id: str, category: str) -> tuple[str, str]:
    if not isinstance(raw, dict):
        raise CandidatePackError(f"{candidate_id}/{category}: clip must be an object")
    path = str(raw.get("path", ""))
    sha = str(raw.get("sha256", "")).lower()
    if not path or not SHA256.fullmatch(sha):
        raise CandidatePackError(f"{candidate_id}/{category}: invalid clip metadata")
    return path, sha


def _load_manifest(path: Path, pack_hash: str) -> PackManifest:
    try:
        if path.stat().st_size > MAX_MANIFEST_BYTES:
            raise CandidatePackError("manifest.json is too large")
        data = json.loads(path.read_text(encoding="utf-8"))
    except CandidatePackError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CandidatePackError("Invalid manifest.json") from exc

    if not isinstance(data, dict):
        raise CandidatePackError("manifest.json must contain an object")

    model_id = str(data.get("model_id", ""))
    model_revision = str(data.get("model_revision", "")).lower()
    persona_hash = str(data.get("persona_hash", "")).lower()
    if model_id != "openbmb/VoxCPM2":
        raise CandidatePackError(f"Unexpected design model: {model_id}")
    if not REVISION.fullmatch(model_revision):
        raise CandidatePackError("model_revision must be an immutable 40-character SHA")
    if not SHA256.fullmatch(persona_hash):
        raise CandidatePackError("persona_hash must be SHA-256")

    raw_candidates = data.get("candidates")
    if not isinstance(raw_candidates, list) or not (1 <= len(raw_candidates) <= 12):
        raise CandidatePackError("manifest must contain between 1 and 12 candidates")

    seen: set[str] = set()
    candidates: list[CandidateManifest] = []
    root = path.parent.resolve()

    for raw in raw_candidates:
        if not isinstance(raw, dict):
            raise CandidatePackError("candidate entry must be an object")
        candidate_id = str(raw.get("candidate_id", ""))
        if not SAFE_ID.fullmatch(candidate_id) or candidate_id in seen:
            raise CandidatePackError(f"Invalid or duplicate candidate_id: {candidate_id!r}")
        seen.add(candidate_id)

        try:
            seed = int(raw["seed"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CandidatePackError(f"{candidate_id}: seed must be an integer") from exc
        if not (0 <= seed <= 2**31 - 1):
            raise CandidatePackError(f"{candidate_id}: seed is out of range")

        candidate_persona_hash = str(raw.get("persona_hash", "")).lower()
        candidate_revision = str(raw.get("model_revision", "")).lower()
        if candidate_persona_hash != persona_hash:
            raise CandidatePackError(f"{candidate_id}: persona hash differs from pack")
        if candidate_revision != model_revision:
            raise CandidatePackError(f"{candidate_id}: model revision differs from pack")

        reference = raw.get("reference")
        clips = raw.get("clips")
        if not isinstance(reference, dict) or not isinstance(clips, dict):
            raise CandidatePackError(f"{candidate_id}: reference and clips objects are required")
        if set(clips) != REQUIRED_CLIPS:
            missing = sorted(REQUIRED_CLIPS - set(clips))
            extra = sorted(set(clips) - REQUIRED_CLIPS)
            raise CandidatePackError(f"{candidate_id}: clip set mismatch; missing={missing}, extra={extra}")

        reference_path = str(reference.get("path", ""))
        reference_sha = str(reference.get("sha256", "")).lower()
        transcript = str(reference.get("transcript", "")).strip()
        if (
            not reference_path
            or not transcript
            or len(transcript) > 1000
            or not SHA256.fullmatch(reference_sha)
        ):
            raise CandidatePackError(f"{candidate_id}: invalid reference metadata")
        _validated_audio(root, reference_path, reference_sha, f"{candidate_id}/reference")

        clip_paths: dict[str, str] = {}
        clip_hashes: dict[str, str] = {}
        for category, raw_clip in clips.items():
            clip_path, clip_sha = _parse_clip(raw_clip, candidate_id, category)
            _validated_audio(root, clip_path, clip_sha, f"{candidate_id}/{category}")
            clip_paths[category] = clip_path
            clip_hashes[category] = clip_sha

        candidates.append(
            CandidateManifest(
                candidate_id=candidate_id,
                seed=seed,
                persona_hash=candidate_persona_hash,
                model_revision=candidate_revision,
                reference_path=reference_path,
                reference_sha256=reference_sha,
                reference_transcript=transcript,
                clips=clip_paths,
                clip_sha256=clip_hashes,
            )
        )

    return PackManifest(
        pack_hash=pack_hash,
        model_id=model_id,
        model_revision=model_revision,
        persona_hash=persona_hash,
        candidates=candidates,
        import_timestamp=str(data.get("created_at", "")),
    )


def import_candidate_pack(zip_path: str | Path, target_root: str | Path) -> PackManifest:
    zip_path = Path(zip_path).expanduser().resolve(strict=True)
    target_root = Path(target_root).expanduser().resolve()
    if not zipfile.is_zipfile(zip_path):
        raise CandidatePackError("Candidate pack is not a ZIP file")

    pack_hash = _sha256_file(zip_path)[:16]
    final_dir = target_root / pack_hash
    if final_dir.exists():
        return _load_manifest(final_dir / "manifest.json", pack_hash)

    target_root.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(prefix=f".{pack_hash}.", dir=target_root))
    try:
        with zipfile.ZipFile(zip_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_FILES:
                raise CandidatePackError(f"Too many ZIP entries: {len(entries)}")
            total = sum(entry.file_size for entry in entries)
            if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise CandidatePackError("Candidate pack is too large")

            names: set[str] = set()
            for entry in entries:
                member = _validate_entry(entry)
                normalized_name = member.as_posix()
                if normalized_name in names:
                    raise CandidatePackError(f"Duplicate ZIP entry: {normalized_name}")
                names.add(normalized_name)
                destination = temp_dir.joinpath(*member.parts)
                destination.resolve().relative_to(temp_dir.resolve())
                if entry.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry) as source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

        manifest = _load_manifest(temp_dir / "manifest.json", pack_hash)
        os.replace(temp_dir, final_dir)
        return manifest
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
