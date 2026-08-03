"""Prometheus-branded entry point for the Arena benchmark.

The legacy ``run_adam_arena.py`` entry point remains available so existing
automation does not break.
"""

from __future__ import annotations

import asyncio

from run_adam_arena import _configure_console, _parse_args, _run


if __name__ == "__main__":
    _configure_console()
    raise SystemExit(asyncio.run(_run(_parse_args())))
