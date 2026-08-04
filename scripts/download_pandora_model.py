from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download


REQUIRED = [
    "ve.pt",
    "t3_mtl23ls_v3.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
    "conds.pt",
    "Cangjie5_TC.json",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--cache-dir", required=True)
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    runtime = config["production_runtime"]
    snapshot = Path(
        snapshot_download(
            repo_id=runtime["model_id"],
            repo_type="model",
            revision=runtime["revision"],
            cache_dir=args.cache_dir,
            allow_patterns=REQUIRED,
        )
    )
    missing = [name for name in REQUIRED if not (snapshot / name).is_file()]
    if missing:
        raise SystemExit(f"Incomplete model snapshot; missing: {', '.join(missing)}")
    print(json.dumps({"snapshot": str(snapshot), "revision": runtime["revision"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
