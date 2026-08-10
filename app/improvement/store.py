from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
import uuid


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ImprovementStore:
    """Local SQLite ledger for verified experience and shadow candidates."""

    def __init__(self, path: Path, *, enabled: bool = True) -> None:
        self.path = path.expanduser().resolve()
        self.enabled = enabled
        self._initialized = False
        self._lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    async def initialize(self) -> None:
        if not self.enabled or self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._initialize_sync)
            self._initialized = True

    def _initialize_sync(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS orientation_entries (
                    id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    path TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT,
                    hits INTEGER NOT NULL DEFAULT 0,
                    verified_successes INTEGER NOT NULL DEFAULT 0,
                    verified_failures INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_key, path, kind)
                );
                CREATE INDEX IF NOT EXISTS idx_orientation_project
                    ON orientation_entries(project_key, updated_at);

                CREATE TABLE IF NOT EXISTS experience_episodes (
                    id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    command_id TEXT,
                    task_id TEXT,
                    task_signature TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    title TEXT NOT NULL,
                    language TEXT,
                    risk TEXT,
                    verification TEXT,
                    success INTEGER NOT NULL,
                    failure_kind TEXT,
                    route_key TEXT,
                    model TEXT,
                    files_json TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    recalled_strategy_ids_json TEXT NOT NULL,
                    recalled_orientation_ids_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(project_key, command_id, task_id, success)
                );
                CREATE INDEX IF NOT EXISTS idx_episode_signature
                    ON experience_episodes(project_key, task_signature, created_at);

                CREATE TABLE IF NOT EXISTS strategy_cards (
                    id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    task_signature TEXT NOT NULL,
                    title TEXT NOT NULL,
                    instruction TEXT NOT NULL,
                    helpful INTEGER NOT NULL DEFAULT 0,
                    harmful INTEGER NOT NULL DEFAULT 0,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'active',
                    source_episode_ids_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(project_key, task_signature, instruction)
                );
                CREATE INDEX IF NOT EXISTS idx_strategy_project
                    ON strategy_cards(project_key, state, updated_at);

                CREATE TABLE IF NOT EXISTS improvement_candidates (
                    id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    evaluation_json TEXT,
                    previous_active_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_candidate_project
                    ON improvement_candidates(project_key, status, updated_at);

                CREATE TABLE IF NOT EXISTS active_policies (
                    project_key TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    activated_at TEXT NOT NULL,
                    PRIMARY KEY(project_key, kind)
                );

                CREATE TABLE IF NOT EXISTS benchmark_runs (
                    id TEXT PRIMARY KEY,
                    project_key TEXT NOT NULL,
                    candidate_id TEXT,
                    score REAL NOT NULL,
                    passed INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    details_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            connection.commit()

    async def upsert_orientation(
        self,
        *,
        project_key: str,
        path: str,
        source_sha256: str,
        kind: str,
        content: str,
        embedding: list[float] | None = None,
    ) -> str:
        await self.initialize()
        if not self.enabled:
            return ""
        return await asyncio.to_thread(
            self._upsert_orientation_sync,
            project_key,
            path,
            source_sha256,
            kind,
            content,
            embedding,
        )

    def _upsert_orientation_sync(
        self,
        project_key: str,
        path: str,
        source_sha256: str,
        kind: str,
        content: str,
        embedding: list[float] | None,
    ) -> str:
        entry_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{project_key}:{path}:{kind}"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO orientation_entries(
                    id, project_key, path, source_sha256, kind, content,
                    embedding_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_key, path, kind) DO UPDATE SET
                    source_sha256=excluded.source_sha256,
                    content=excluded.content,
                    embedding_json=COALESCE(
                        excluded.embedding_json,
                        orientation_entries.embedding_json
                    ),
                    updated_at=excluded.updated_at
                """,
                (
                    entry_id,
                    project_key,
                    path,
                    source_sha256,
                    kind,
                    content,
                    json.dumps(embedding) if embedding else None,
                    _utc_now(),
                ),
            )
            connection.commit()
        return entry_id

    async def recall_rows(
        self,
        *,
        project_key: str,
        limit: int = 200,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        await self.initialize()
        if not self.enabled:
            return [], []
        return await asyncio.to_thread(
            self._recall_rows_sync,
            project_key,
            limit,
        )

    def _recall_rows_sync(
        self,
        project_key: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        with self._connect() as connection:
            orientations = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM orientation_entries
                    WHERE project_key=?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (project_key, limit),
                ).fetchall()
            ]
            strategies = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM strategy_cards
                    WHERE project_key=? AND state='active'
                    ORDER BY evidence_count DESC, helpful DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (project_key, limit),
                ).fetchall()
            ]
        return orientations, strategies

    async def mark_recalled(self, ids: list[str]) -> None:
        await self.initialize()
        if not self.enabled or not ids:
            return
        await asyncio.to_thread(self._mark_recalled_sync, ids)

    def _mark_recalled_sync(self, ids: list[str]) -> None:
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE orientation_entries SET hits=hits+1 WHERE id IN ({placeholders})",
                ids,
            )
            connection.commit()

    async def set_orientation_embedding(
        self,
        entry_id: str,
        embedding: list[float],
    ) -> None:
        await self.initialize()
        if not self.enabled or not entry_id or not embedding:
            return
        await asyncio.to_thread(
            self._set_orientation_embedding_sync,
            entry_id,
            embedding,
        )

    def _set_orientation_embedding_sync(
        self,
        entry_id: str,
        embedding: list[float],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE orientation_entries SET embedding_json=?, updated_at=? "
                "WHERE id=?",
                (json.dumps(embedding), _utc_now(), entry_id),
            )
            connection.commit()

    async def record_episode(self, episode: dict[str, Any]) -> str:
        await self.initialize()
        if not self.enabled:
            return ""
        return await asyncio.to_thread(self._record_episode_sync, episode)

    def _record_episode_sync(self, episode: dict[str, Any]) -> str:
        episode_id = str(uuid.uuid4())
        success = bool(episode.get("success"))
        strategy_ids = list(episode.get("recalled_strategy_ids") or [])
        orientation_ids = list(episode.get("recalled_orientation_ids") or [])
        now = _utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO experience_episodes(
                    id, project_key, command_id, task_id, task_signature,
                    goal, title, language, risk, verification, success,
                    failure_kind, route_key, model, files_json, evidence_json,
                    recalled_strategy_ids_json, recalled_orientation_ids_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    episode_id,
                    episode["project_key"],
                    episode.get("command_id"),
                    episode.get("task_id"),
                    episode["task_signature"],
                    episode.get("goal", "")[:8_000],
                    episode.get("title", "")[:1_000],
                    episode.get("language"),
                    episode.get("risk"),
                    episode.get("verification"),
                    int(success),
                    episode.get("failure_kind"),
                    episode.get("route_key"),
                    episode.get("model"),
                    json.dumps(episode.get("files") or [], ensure_ascii=False),
                    json.dumps(episode.get("evidence") or [], ensure_ascii=False),
                    json.dumps(strategy_ids),
                    json.dumps(orientation_ids),
                    now,
                ),
            )
            if strategy_ids:
                placeholders = ",".join("?" for _ in strategy_ids)
                column = "helpful" if success else "harmful"
                connection.execute(
                    f"UPDATE strategy_cards SET {column}={column}+1, "
                    f"evidence_count=evidence_count+1, updated_at=? "
                    f"WHERE id IN ({placeholders})",
                    [now, *strategy_ids],
                )
            if orientation_ids:
                placeholders = ",".join("?" for _ in orientation_ids)
                column = "verified_successes" if success else "verified_failures"
                connection.execute(
                    f"UPDATE orientation_entries SET {column}={column}+1 "
                    f"WHERE id IN ({placeholders})",
                    orientation_ids,
                )
            connection.commit()
        return episode_id

    async def upsert_strategy(
        self,
        *,
        project_key: str,
        task_signature: str,
        title: str,
        instruction: str,
        source_episode_id: str,
    ) -> str:
        await self.initialize()
        return await asyncio.to_thread(
            self._upsert_strategy_sync,
            project_key,
            task_signature,
            title,
            instruction,
            source_episode_id,
        )

    def _upsert_strategy_sync(
        self,
        project_key: str,
        task_signature: str,
        title: str,
        instruction: str,
        source_episode_id: str,
    ) -> str:
        strategy_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{project_key}:{task_signature}:{instruction}",
            )
        )
        now = _utc_now()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT source_episode_ids_json FROM strategy_cards WHERE id=?",
                (strategy_id,),
            ).fetchone()
            sources = json.loads(row[0]) if row else []
            if source_episode_id and source_episode_id not in sources:
                sources.append(source_episode_id)
            connection.execute(
                """
                INSERT INTO strategy_cards(
                    id, project_key, task_signature, title, instruction,
                    evidence_count, source_episode_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(project_key, task_signature, instruction) DO UPDATE SET
                    evidence_count=strategy_cards.evidence_count+1,
                    source_episode_ids_json=excluded.source_episode_ids_json,
                    updated_at=excluded.updated_at
                """,
                (
                    strategy_id,
                    project_key,
                    task_signature,
                    title,
                    instruction,
                    json.dumps(sources),
                    now,
                ),
            )
            connection.commit()
        return strategy_id

    async def list_table(
        self,
        table: str,
        *,
        project_key: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        allowed = {
            "experience_episodes",
            "strategy_cards",
            "orientation_entries",
            "improvement_candidates",
            "benchmark_runs",
        }
        if table not in allowed:
            raise ValueError("Unsupported improvement table.")
        await self.initialize()
        return await asyncio.to_thread(
            self._list_table_sync,
            table,
            project_key,
            limit,
        )

    async def get_episode(self, episode_id: str, *, project_key: str) -> dict[str, Any]:
        await self.initialize()
        row = await asyncio.to_thread(self._get_episode_sync, episode_id, project_key)
        if row is None:
            raise KeyError(episode_id)
        return row

    def _get_episode_sync(self, episode_id: str, project_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM experience_episodes WHERE id=? AND project_key=? LIMIT 1",
                (episode_id, project_key),
            ).fetchone()
        return dict(row) if row else None

    async def get_benchmark(self, run_id: str, *, project_key: str) -> dict[str, Any]:
        await self.initialize()
        row = await asyncio.to_thread(self._get_benchmark_sync, run_id, project_key)
        if row is None:
            raise KeyError(run_id)
        return row

    def _get_benchmark_sync(self, run_id: str, project_key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM benchmark_runs WHERE id=? AND project_key=? LIMIT 1",
                (run_id, project_key),
            ).fetchone()
        return dict(row) if row else None

    def _list_table_sync(
        self,
        table: str,
        project_key: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} WHERE project_key=? "
                    "ORDER BY created_at DESC LIMIT ?"
                    if table in {
                        "experience_episodes",
                        "improvement_candidates",
                        "benchmark_runs",
                    }
                    else f"SELECT * FROM {table} WHERE project_key=? "
                    "ORDER BY updated_at DESC LIMIT ?",
                    (project_key, max(1, min(limit, 1_000))),
                ).fetchall()
            ]

    async def status(self, *, project_key: str) -> dict[str, Any]:
        await self.initialize()
        if not self.enabled:
            return {"enabled": False}
        return await asyncio.to_thread(self._status_sync, project_key)

    def _status_sync(self, project_key: str) -> dict[str, Any]:
        tables = {
            "episodes": "experience_episodes",
            "strategies": "strategy_cards",
            "orientation_entries": "orientation_entries",
            "candidates": "improvement_candidates",
            "benchmark_runs": "benchmark_runs",
        }
        with self._connect() as connection:
            counts = {
                label: int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE project_key=?",
                        (project_key,),
                    ).fetchone()[0]
                )
                for label, table in tables.items()
            }
            active = [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM active_policies WHERE project_key=?",
                    (project_key,),
                ).fetchall()
            ]
        return {"enabled": True, **counts, "active_policies": active}

    async def create_candidate(
        self,
        *,
        project_key: str,
        kind: str,
        title: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        await self.initialize()
        candidate_id = f"cand_{uuid.uuid4().hex[:16]}"
        now = _utc_now()
        await asyncio.to_thread(
            self._create_candidate_sync,
            candidate_id,
            project_key,
            kind,
            title,
            payload,
            now,
        )
        return await self.get_candidate(candidate_id, project_key=project_key)

    def _create_candidate_sync(
        self,
        candidate_id: str,
        project_key: str,
        kind: str,
        title: str,
        payload: dict[str, Any],
        now: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO improvement_candidates(
                    id, project_key, kind, title, status, payload_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'proposed', ?, ?, ?)
                """,
                (
                    candidate_id,
                    project_key,
                    kind,
                    title,
                    json.dumps(payload, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            connection.commit()

    async def get_candidate(
        self,
        candidate_id: str,
        *,
        project_key: str,
    ) -> dict[str, Any]:
        await self.initialize()
        result = await asyncio.to_thread(
            self._get_candidate_sync,
            candidate_id,
            project_key,
        )
        if result is None:
            raise KeyError(candidate_id)
        return result

    def _get_candidate_sync(
        self,
        candidate_id: str,
        project_key: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM improvement_candidates WHERE id=? AND project_key=?",
                (candidate_id, project_key),
            ).fetchone()
        return dict(row) if row else None

    async def set_candidate_evaluation(
        self,
        *,
        candidate_id: str,
        project_key: str,
        evaluation: dict[str, Any],
        passed: bool,
    ) -> dict[str, Any]:
        await self.initialize()
        await asyncio.to_thread(
            self._set_candidate_evaluation_sync,
            candidate_id,
            project_key,
            evaluation,
            passed,
        )
        return await self.get_candidate(candidate_id, project_key=project_key)

    def _set_candidate_evaluation_sync(
        self,
        candidate_id: str,
        project_key: str,
        evaluation: dict[str, Any],
        passed: bool,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE improvement_candidates
                SET status=?, evaluation_json=?, updated_at=?
                WHERE id=? AND project_key=?
                """,
                (
                    "evaluated" if passed else "rejected",
                    json.dumps(evaluation, ensure_ascii=False),
                    _utc_now(),
                    candidate_id,
                    project_key,
                ),
            )
            connection.commit()

    async def promote_candidate(
        self,
        *,
        candidate_id: str,
        project_key: str,
    ) -> dict[str, Any]:
        await self.initialize()
        await asyncio.to_thread(
            self._promote_candidate_sync,
            candidate_id,
            project_key,
        )
        return await self.get_candidate(candidate_id, project_key=project_key)

    async def active_candidates(
        self,
        *,
        project_key: str,
    ) -> list[dict[str, Any]]:
        await self.initialize()
        return await asyncio.to_thread(
            self._active_candidates_sync,
            project_key,
        )

    def _active_candidates_sync(
        self,
        project_key: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT c.* FROM active_policies p
                    JOIN improvement_candidates c ON c.id=p.candidate_id
                    WHERE p.project_key=? ORDER BY c.kind
                    """,
                    (project_key,),
                ).fetchall()
            ]

    async def rollback_candidate(
        self,
        *,
        candidate_id: str,
        project_key: str,
    ) -> dict[str, Any]:
        await self.initialize()
        await asyncio.to_thread(
            self._rollback_candidate_sync,
            candidate_id,
            project_key,
        )
        return await self.get_candidate(candidate_id, project_key=project_key)

    def _rollback_candidate_sync(
        self,
        candidate_id: str,
        project_key: str,
    ) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT kind, status, previous_active_id "
                "FROM improvement_candidates WHERE id=? AND project_key=?",
                (candidate_id, project_key),
            ).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            active = connection.execute(
                "SELECT candidate_id FROM active_policies "
                "WHERE project_key=? AND kind=?",
                (project_key, row["kind"]),
            ).fetchone()
            if active is None or active["candidate_id"] != candidate_id:
                raise ValueError("Candidate is not the active policy.")
            previous_id = row["previous_active_id"]
            if previous_id:
                connection.execute(
                    """
                    UPDATE active_policies SET candidate_id=?, activated_at=?
                    WHERE project_key=? AND kind=?
                    """,
                    (previous_id, now, project_key, row["kind"]),
                )
                connection.execute(
                    "UPDATE improvement_candidates SET status='promoted', "
                    "updated_at=? WHERE id=?",
                    (now, previous_id),
                )
            else:
                connection.execute(
                    "DELETE FROM active_policies WHERE project_key=? AND kind=?",
                    (project_key, row["kind"]),
                )
            connection.execute(
                "UPDATE improvement_candidates SET status='rolled_back', "
                "updated_at=? WHERE id=?",
                (now, candidate_id),
            )
            connection.commit()

    def _promote_candidate_sync(
        self,
        candidate_id: str,
        project_key: str,
    ) -> None:
        now = _utc_now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT kind, status FROM improvement_candidates "
                "WHERE id=? AND project_key=?",
                (candidate_id, project_key),
            ).fetchone()
            if row is None:
                raise KeyError(candidate_id)
            if row["status"] != "evaluated":
                raise ValueError("Only a passing evaluated candidate can be promoted.")
            previous = connection.execute(
                "SELECT candidate_id FROM active_policies "
                "WHERE project_key=? AND kind=?",
                (project_key, row["kind"]),
            ).fetchone()
            previous_id = previous["candidate_id"] if previous else None
            connection.execute(
                """
                INSERT INTO active_policies(
                    project_key, kind, candidate_id, activated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(project_key, kind) DO UPDATE SET
                    candidate_id=excluded.candidate_id,
                    activated_at=excluded.activated_at
                """,
                (project_key, row["kind"], candidate_id, now),
            )
            connection.execute(
                """
                UPDATE improvement_candidates
                SET status='promoted', previous_active_id=?, updated_at=?
                WHERE id=? AND project_key=?
                """,
                (previous_id, now, candidate_id, project_key),
            )
            connection.commit()

    async def record_benchmark(
        self,
        *,
        project_key: str,
        candidate_id: str | None,
        score: float,
        passed: int,
        total: int,
        details: dict[str, Any],
    ) -> str:
        await self.initialize()
        run_id = f"bench_{uuid.uuid4().hex[:16]}"
        await asyncio.to_thread(
            self._record_benchmark_sync,
            run_id,
            project_key,
            candidate_id,
            score,
            passed,
            total,
            details,
        )
        return run_id

    def _record_benchmark_sync(
        self,
        run_id: str,
        project_key: str,
        candidate_id: str | None,
        score: float,
        passed: int,
        total: int,
        details: dict[str, Any],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO benchmark_runs(
                    id, project_key, candidate_id, score, passed, total,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    project_key,
                    candidate_id,
                    score,
                    passed,
                    total,
                    json.dumps(details, ensure_ascii=False),
                    _utc_now(),
                ),
            )
            connection.commit()
