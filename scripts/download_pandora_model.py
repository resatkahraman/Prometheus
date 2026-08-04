from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

_HEX40 = re.compile(r"^[0-9a-f]{40}$")

REQUIRED = [
    "ve.pt",
    "t3_mtl23ls_v3.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
    "conds.pt",
    "Cangjie5_TC.json",
]


def _sanitize_path(path: str | Path) -> str:
    s = str(path)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data and local_app_data in s:
        s = s.replace(local_app_data, "%LOCALAPPDATA%")
    user_home = str(Path.home())
    if user_home and user_home in s:
        s = s.replace(user_home, "~")
    return s


def check_existing_snapshot(cache_dir: Path) -> Path | None:
    if not cache_dir.exists():
        return None
    for root, _, files in os.walk(cache_dir):
        root_path = Path(root)
        if all((root_path / f).is_file() and (root_path / f).stat().st_size > 0 for f in REQUIRED):
            return root_path
    return None


def get_estimated_size_via_api(repo_id: str, revision: str) -> tuple[int | None, str]:
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        info = api.model_info(repo_id=repo_id, revision=revision, files_metadata=True)
        total_bytes = 0
        if info and hasattr(info, "siblings") and info.siblings:
            for s in info.siblings:
                r_filename = getattr(s, "rfilename", "")
                if r_filename in REQUIRED:
                    size = getattr(s, "size", None)
                    if size is not None:
                        total_bytes += size
        return (total_bytes if total_bytes > 0 else None, "ok")
    except Exception as exc:
        exc_str = str(exc).lower()
        if any(w in exc_str for w in ("getaddrinfo", "nameresolution", "dns", "gai", "connection", "connecttimeout")):
            return (None, "unreachable (corporate DNS block)")
        return (None, f"metadata_unavailable ({type(exc).__name__})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download or verify Pandora Voice Chatterbox Multilingual V3 model.")
    parser.add_argument("--config", required=True, help="Path to pandora_voice_models.json")
    parser.add_argument("--cache-dir", required=True, help="Target cache directory for model snapshot")
    parser.add_argument("--dry-run", action="store_true", help="Print download plan without fetching files")
    parser.add_argument("--force", action="store_true", help="Force re-download even if required files exist locally")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_file():
        print(f"Hata: Yapılandırma dosyası bulunamadı: {config_path}", file=sys.stderr)
        return 1

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Hata: Yapılandırma okunamadı: {exc}", file=sys.stderr)
        return 1

    runtime = config.get("production_runtime")
    if not isinstance(runtime, dict):
        print("Hata: Yapılandırmada 'production_runtime' objesi eksik.", file=sys.stderr)
        return 1

    repo_id = str(runtime.get("model_id", "ResembleAI/chatterbox"))
    revision = str(runtime.get("revision", ""))
    if not _HEX40.fullmatch(revision):
        print(f"Hata: Geçersiz veya sabitlenmemiş revision SHA: '{revision}'. Pinned 40-character SHA zorunludur.", file=sys.stderr)
        return 1

    cache_dir = Path(args.cache_dir).expanduser().resolve()

    if not args.force:
        existing = check_existing_snapshot(cache_dir)
        if existing is not None:
            res_payload = {
                "status": "already_present",
                "snapshot": _sanitize_path(existing),
                "revision": revision,
                "required_files": REQUIRED,
            }
            print(json.dumps(res_payload, ensure_ascii=False))
            return 0

    if args.dry_run:
        est_size, net_status = get_estimated_size_via_api(repo_id, revision)
        dry_payload = {
            "dry_run": True,
            "repo_id": repo_id,
            "revision": revision,
            "cache_dir": _sanitize_path(cache_dir),
            "required_files": REQUIRED,
            "estimated_download_size_bytes": est_size,
            "network_status": net_status,
        }
        print(json.dumps(dry_payload, ensure_ascii=False, indent=2))
        return 0

    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError, RevisionNotFoundError
    except ImportError as exc:
        print(f"Bağımlılık Hatası: huggingface_hub modülü venv içinde bulunamadı: {exc}", file=sys.stderr)
        return 2

    try:
        free_bytes = shutil.disk_usage(cache_dir.parent if cache_dir.parent.exists() else cache_dir.anchor).free
        if free_bytes < 5 * 1024**3:
            print(f"Disk Yetersizliği Hatası: Model indirimi için yeterli boş alan yok (Mevcut: {free_bytes // (1024**2)} MiB).", file=sys.stderr)
            return 5
    except Exception:
        pass

    try:
        snapshot_raw = snapshot_download(
            repo_id=repo_id,
            repo_type="model",
            revision=revision,
            cache_dir=str(cache_dir),
            allow_patterns=REQUIRED,
            resume_download=True,
        )
        snapshot = Path(snapshot_raw)
    except (RepositoryNotFoundError, RevisionNotFoundError, EntryNotFoundError) as exc:
        print(f"Model Revision Bulunamadı: Repo ('{repo_id}') veya revision ('{revision}') mevcut değil: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        exc_str = str(exc)
        exc_lower = exc_str.lower()
        if any(w in exc_lower for w in ("getaddrinfo", "nameresolution", "dns", "gai", "huggingface.co", "maxretryerror", "connecttimeout")):
            print(
                "Ağ/DNS Hatası: Şirket ağında huggingface.co adresine erişilemiyor. "
                "Model indirme ev internetinde yapılmalıdır.",
                file=sys.stderr,
            )
            return 3
        elif "connection" in exc_lower or "timeout" in exc_lower:
            print(f"Bağımlı Sunucu Bağlantı Hatası: Hugging Face sunucusuna bağlanılamadı: {exc_str}", file=sys.stderr)
            return 3
        elif "space" in exc_lower or "disk" in exc_lower or "nospc" in exc_lower:
            print(f"Disk Yetersizliği Hatası: Model indirimi için yeterli boş alan yok: {exc_str}", file=sys.stderr)
            return 5
        else:
            print(f"Model İndirme Hatası ({type(exc).__name__}): {exc_str}", file=sys.stderr)
            return 3

    missing = [name for name in REQUIRED if not (snapshot / name).is_file() or (snapshot / name).stat().st_size == 0]
    if missing:
        print(f"Model Dosyaları Eksik/Bozuk: Required dosyalar eksik: {', '.join(missing)}", file=sys.stderr)
        return 6

    print(json.dumps({"snapshot": _sanitize_path(snapshot), "revision": revision, "status": "downloaded"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
