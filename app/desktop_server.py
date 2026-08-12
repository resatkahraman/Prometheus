"""Loopback-only ASGI runner for the native Prometheus Desktop transport."""

from __future__ import annotations

import os

CORE_HOST = "127.0.0.1"
DEFAULT_CORE_PORT = 8765
CORE_PORT_ENV = "PROMETHEUS_DESKTOP_CORE_PORT"


def resolve_core_port(value: str | None = None) -> int:
    candidate = value if value is not None else os.getenv(CORE_PORT_ENV)
    if candidate is None or not candidate.strip():
        return DEFAULT_CORE_PORT
    try:
        port = int(candidate.strip())
    except (TypeError, ValueError):
        return DEFAULT_CORE_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_CORE_PORT


def main() -> None:
    import uvicorn
    from app.main import app

    uvicorn.run(app, host=CORE_HOST, port=resolve_core_port(), reload=False)


if __name__ == "__main__":
    main()
