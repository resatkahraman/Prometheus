from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from app.arena.models import ArenaResult


class ArenaStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS arena_runs (
                    run_id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL,
                    mission_id TEXT,
                    status TEXT NOT NULL,
                    score REAL NOT NULL,
                    elapsed_seconds REAL NOT NULL,
                    model_calls INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    approvals INTEGER NOT NULL,
                    decisions INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_arena_runs_scenario_created
                ON arena_runs(scenario_id, created_at DESC)
                """
            )
            connection.commit()

    def record(self, result: ArenaResult) -> None:
        self.initialize()
        payload = result.to_dict()
        usage = result.usage
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO arena_runs(
                    run_id, scenario_id, mission_id, status, score,
                    elapsed_seconds, model_calls, total_tokens,
                    approvals, decisions, result_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.run_id,
                    result.scenario_id,
                    result.mission_id,
                    result.status,
                    result.score.total,
                    result.elapsed_seconds,
                    int(
                        usage.get(
                            "model_calls",
                            usage.get("events", 0),
                        )
                    ),
                    int(usage.get("total_tokens", 0)),
                    result.approvals_applied,
                    result.decisions_answered,
                    json.dumps(payload, ensure_ascii=False),
                    time.time(),
                ),
            )
            connection.commit()

    def history(
        self,
        *,
        scenario_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as connection:
            if scenario_id:
                rows = connection.execute(
                    """
                    SELECT * FROM arena_runs
                    WHERE scenario_id=?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (scenario_id, max(1, limit)),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT * FROM arena_runs
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (max(1, limit),),
                ).fetchall()
        return [dict(row) for row in rows]
