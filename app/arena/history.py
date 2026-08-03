from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class ArenaHistoryReader:
    """Read-only aggregation for Arena SQLite result databases."""

    def __init__(self, directory: Path, *, max_databases: int = 100) -> None:
        self.directory = directory.resolve()
        self.max_databases = max(1, max_databases)

    def databases(self) -> tuple[Path, ...]:
        if not self.directory.is_dir():
            return ()
        candidates: list[Path] = []
        for path in self.directory.glob("arena*.db"):
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                continue
            if path.is_symlink() or not resolved.is_file():
                continue
            if resolved.parent != self.directory:
                continue
            candidates.append(resolved)
        candidates.sort(key=lambda item: item.name.lower())
        return tuple(candidates[: self.max_databases])

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro",
            uri=True,
            timeout=5,
        )
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _summary(row: sqlite3.Row, *, database: str) -> dict[str, Any]:
        try:
            payload = json.loads(row["result_json"])
        except (json.JSONDecodeError, TypeError):
            payload = {}
        return {
            "run_id": row["run_id"],
            "scenario_id": row["scenario_id"],
            "scenario_title": payload.get("scenario_title", row["scenario_id"]),
            "mission_id": row["mission_id"],
            "status": row["status"],
            "score": float(row["score"]),
            "elapsed_seconds": float(row["elapsed_seconds"]),
            "model_calls": int(row["model_calls"]),
            "total_tokens": int(row["total_tokens"]),
            "approvals": int(row["approvals"]),
            "decisions": int(row["decisions"]),
            "created_at": float(row["created_at"]),
            "database": database,
        }

    def history(
        self,
        *,
        scenario_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        wanted = scenario_id.strip().lower() if scenario_id else None
        for path in self.databases():
            try:
                with self._connect(path) as connection:
                    if wanted:
                        result = connection.execute(
                            """
                            SELECT * FROM arena_runs
                            WHERE lower(scenario_id)=?
                            ORDER BY created_at DESC
                            LIMIT ?
                            """,
                            (wanted, max(1, limit)),
                        ).fetchall()
                    else:
                        result = connection.execute(
                            """
                            SELECT * FROM arena_runs
                            ORDER BY created_at DESC
                            LIMIT ?
                            """,
                            (max(1, limit),),
                        ).fetchall()
                rows.extend(
                    self._summary(row, database=path.name)
                    for row in result
                )
            except (sqlite3.Error, OSError):
                continue
        rows.sort(key=lambda item: item["created_at"], reverse=True)
        return rows[: max(1, limit)]

    def get(self, run_id: str) -> dict[str, Any] | None:
        normalized = run_id.strip()
        if not normalized:
            return None
        for path in self.databases():
            try:
                with self._connect(path) as connection:
                    row = connection.execute(
                        "SELECT result_json FROM arena_runs WHERE run_id=?",
                        (normalized,),
                    ).fetchone()
                if row is None:
                    continue
                payload = json.loads(row["result_json"])
                if not isinstance(payload, dict):
                    continue
                payload["database"] = path.name
                return payload
            except (sqlite3.Error, OSError, json.JSONDecodeError, TypeError):
                continue
        return None
