"""Loopback-only ASGI runner for the native Prometheus Desktop transport."""

from __future__ import annotations

import os
import sys
from typing import TextIO

CORE_HOST = "127.0.0.1"
DEFAULT_CORE_PORT = 8765
CORE_PORT_ENV = "PROMETHEUS_CORE_PORT"
_STDIO_SINKS: list[TextIO] = []


class _NonInteractiveSink:
    def __init__(self) -> None:
        self._stream = open(os.devnull, "w", encoding="utf-8", buffering=1)

    def isatty(self) -> bool:
        return False

    def write(self, value: str) -> int:
        return self._stream.write(value)

    def flush(self) -> None:
        self._stream.flush()

    def close(self) -> None:
        self._stream.close()

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


def ensure_noninteractive_stdio() -> None:
    """Give frozen --noconsole builds safe, non-TTY logging streams."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            sink = _NonInteractiveSink()
            _STDIO_SINKS.append(sink)
            setattr(sys, name, sink)


def resolve_core_port(value: str | None = None) -> int:
    candidate = value if value is not None else os.getenv(CORE_PORT_ENV) or os.getenv("PROMETHEUS_DESKTOP_CORE_PORT")
    if candidate is None or not candidate.strip():
        return DEFAULT_CORE_PORT
    try:
        port = int(candidate.strip())
    except (TypeError, ValueError):
        return DEFAULT_CORE_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_CORE_PORT


def main() -> None:
    ensure_noninteractive_stdio()
    import uvicorn
    from app.main import app

    uvicorn.run(
        app,
        host=CORE_HOST,
        port=resolve_core_port(),
        reload=False,
        use_colors=False,
    )


if __name__ == "__main__":
    main()
