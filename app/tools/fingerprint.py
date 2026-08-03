from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any


def _normalize_path(value: Any) -> str:
    text = str(value or ".").strip().replace("\\", "/")
    path = PurePosixPath(text)
    return path.as_posix().lstrip("./") or "."


def normalize_tool_arguments(
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> dict[str, Any]:
    source = dict(arguments or {})

    if tool_name == "workspace_write":
        return {
            "path": _normalize_path(source.get("path")),
            "content": str(source.get("content", "")),
        }

    if tool_name == "safe_terminal":
        extra_args = source.get("extra_args", [])
        if not isinstance(extra_args, list):
            extra_args = [extra_args]
        return {
            "preset": str(source.get("preset", "")).strip(),
            "extra_args": [str(item) for item in extra_args],
        }

    normalized: dict[str, Any] = {}
    for key in sorted(source):
        value = source[key]
        if key == "path":
            normalized[key] = _normalize_path(value)
        else:
            normalized[key] = value
    return normalized


def tool_fingerprint(
    tool_name: str,
    arguments: dict[str, Any] | None,
) -> str:
    payload = {
        "tool": tool_name.strip(),
        "arguments": normalize_tool_arguments(tool_name, arguments),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
