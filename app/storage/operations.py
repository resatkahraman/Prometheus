import asyncio
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class OperationsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def utc_day() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS response_cache (
                    cache_key TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS route_daily_usage (
                    usage_day TEXT NOT NULL,
                    route_key TEXT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (usage_day, route_key)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mode_daily_usage (
                    usage_day TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (usage_day, mode)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mission_usage (
                    usage_scope TEXT PRIMARY KEY,
                    reserved_calls INTEGER NOT NULL DEFAULT 0,
                    estimated_input_tokens INTEGER NOT NULL DEFAULT 0,
                    actual_input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS route_stats (
                    route_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    total_calls INTEGER NOT NULL DEFAULT 0,
                    successful_calls INTEGER NOT NULL DEFAULT 0,
                    failed_calls INTEGER NOT NULL DEFAULT 0,
                    total_latency_ms INTEGER NOT NULL DEFAULT 0,
                    total_input_tokens INTEGER NOT NULL DEFAULT 0,
                    total_output_tokens INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    remote_request_limit INTEGER,
                    remote_requests_remaining INTEGER,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS verified_task_route_stats (
                    task_signature TEXT NOT NULL,
                    route_key TEXT NOT NULL,
                    verified_successes INTEGER NOT NULL DEFAULT 0,
                    verified_failures INTEGER NOT NULL DEFAULT 0,
                    total_latency_ms INTEGER NOT NULL DEFAULT 0,
                    total_output_tokens INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY(task_signature, route_key)
                )
                """
            )
            connection.commit()

    async def reserve_mission_call(
        self,
        *,
        usage_scope: str,
        estimated_input_tokens: int,
        max_calls: int,
        max_estimated_input_tokens: int,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._reserve_mission_call_sync,
            usage_scope,
            estimated_input_tokens,
            max_calls,
            max_estimated_input_tokens,
        )

    def _reserve_mission_call_sync(
        self,
        usage_scope: str,
        estimated_input_tokens: int,
        max_calls: int,
        max_estimated_input_tokens: int,
    ) -> dict[str, Any]:
        scope = usage_scope.strip()
        if not scope:
            raise ValueError("Misyon kullanım kapsamı boş olamaz.")
        estimated = max(0, int(estimated_input_tokens))
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT reserved_calls, estimated_input_tokens,
                       actual_input_tokens, output_tokens
                FROM mission_usage
                WHERE usage_scope=?
                """,
                (scope,),
            ).fetchone()
            calls_used = int(row["reserved_calls"]) if row else 0
            estimated_used = (
                int(row["estimated_input_tokens"]) if row else 0
            )
            actual_input = int(row["actual_input_tokens"]) if row else 0
            output_tokens = int(row["output_tokens"]) if row else 0
            calls_allowed = calls_used < max_calls
            tokens_allowed = (
                estimated_used + estimated
                <= max_estimated_input_tokens
            )
            allowed = calls_allowed and tokens_allowed

            if allowed:
                calls_used += 1
                estimated_used += estimated
                connection.execute(
                    """
                    INSERT INTO mission_usage(
                        usage_scope, reserved_calls,
                        estimated_input_tokens, actual_input_tokens,
                        output_tokens, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(usage_scope) DO UPDATE SET
                        reserved_calls=excluded.reserved_calls,
                        estimated_input_tokens=excluded.estimated_input_tokens,
                        updated_at=excluded.updated_at
                    """,
                    (
                        scope,
                        calls_used,
                        estimated_used,
                        actual_input,
                        output_tokens,
                        now,
                    ),
                )
            connection.commit()

        reason = "Misyon ücretsiz bütçesi uygun."
        if not calls_allowed:
            reason = "Misyon model çağrısı bütçesi tükendi."
        elif not tokens_allowed:
            reason = "Misyon tahmini giriş token bütçesi tükendi."
        return {
            "allowed": allowed,
            "usage_scope": scope,
            "calls_used": calls_used,
            "calls_budget": max_calls,
            "estimated_input_tokens_used": estimated_used,
            "estimated_input_tokens_budget": (
                max_estimated_input_tokens
            ),
            "actual_input_tokens": actual_input,
            "output_tokens": output_tokens,
            "reason": reason,
        }

    async def record_mission_tokens(
        self,
        *,
        usage_scope: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        await asyncio.to_thread(
            self._record_mission_tokens_sync,
            usage_scope,
            input_tokens or 0,
            output_tokens or 0,
        )

    def _record_mission_tokens_sync(
        self,
        usage_scope: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE mission_usage
                SET actual_input_tokens=actual_input_tokens + ?,
                    output_tokens=output_tokens + ?,
                    updated_at=?
                WHERE usage_scope=?
                """,
                (
                    max(0, int(input_tokens)),
                    max(0, int(output_tokens)),
                    time.time(),
                    usage_scope.strip(),
                ),
            )
            connection.commit()

    async def mission_usage(
        self,
        usage_scope: str,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            self._mission_usage_sync,
            usage_scope,
        )

    def _mission_usage_sync(
        self,
        usage_scope: str,
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM mission_usage WHERE usage_scope=?",
                (usage_scope.strip(),),
            ).fetchone()
        return dict(row) if row else None

    async def route_requests_today(self, route_key: str) -> int:
        return await asyncio.to_thread(
            self._route_requests_today_sync,
            route_key,
        )

    def _route_requests_today_sync(self, route_key: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT request_count
                FROM route_daily_usage
                WHERE usage_day = ? AND route_key = ?
                """,
                (self.utc_day(), route_key),
            ).fetchone()
            return int(row["request_count"]) if row else 0

    async def increment_route_request(self, route_key: str) -> None:
        await asyncio.to_thread(
            self._increment_route_request_sync,
            route_key,
        )

    def _increment_route_request_sync(self, route_key: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO route_daily_usage(
                    usage_day, route_key, request_count
                )
                VALUES (?, ?, 1)
                ON CONFLICT(usage_day, route_key) DO UPDATE SET
                    request_count = request_count + 1
                """,
                (self.utc_day(), route_key),
            )
            connection.commit()

    async def mode_requests_today(self, mode: str) -> int:
        return await asyncio.to_thread(
            self._mode_requests_today_sync,
            mode,
        )

    def _mode_requests_today_sync(self, mode: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT request_count
                FROM mode_daily_usage
                WHERE usage_day = ? AND mode = ?
                """,
                (self.utc_day(), mode),
            ).fetchone()
            return int(row["request_count"]) if row else 0

    async def increment_mode_request(self, mode: str) -> None:
        await asyncio.to_thread(
            self._increment_mode_request_sync,
            mode,
        )

    def _increment_mode_request_sync(self, mode: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mode_daily_usage(
                    usage_day, mode, request_count
                )
                VALUES (?, ?, 1)
                ON CONFLICT(usage_day, mode) DO UPDATE SET
                    request_count = request_count + 1
                """,
                (self.utc_day(), mode),
            )
            connection.commit()

    async def get_cached(self, cache_key: str) -> str | None:
        return await asyncio.to_thread(self._get_cached_sync, cache_key)

    def _get_cached_sync(self, cache_key: str) -> str | None:
        now = time.time()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT response_json
                FROM response_cache
                WHERE cache_key = ? AND expires_at > ?
                """,
                (cache_key, now),
            ).fetchone()
            if row is None:
                connection.execute(
                    "DELETE FROM response_cache WHERE expires_at <= ?",
                    (now,),
                )
                connection.commit()
                return None
            return str(row["response_json"])

    async def set_cached(
        self,
        cache_key: str,
        response_json: str,
        ttl_seconds: int,
    ) -> None:
        await asyncio.to_thread(
            self._set_cached_sync,
            cache_key,
            response_json,
            ttl_seconds,
        )

    def _set_cached_sync(
        self,
        cache_key: str,
        response_json: str,
        ttl_seconds: int,
    ) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO response_cache(
                    cache_key, response_json, created_at, expires_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
                """,
                (cache_key, response_json, now, now + ttl_seconds),
            )
            connection.commit()

    async def cache_count(self) -> int:
        return await asyncio.to_thread(self._cache_count_sync)

    def _cache_count_sync(self) -> int:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM response_cache WHERE expires_at <= ?",
                (now,),
            )
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM response_cache"
            ).fetchone()
            connection.commit()
            return int(row["count"])

    async def clear_cache(self) -> int:
        return await asyncio.to_thread(self._clear_cache_sync)

    def _clear_cache_sync(self) -> int:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM response_cache")
            connection.commit()
            return int(cursor.rowcount)

    async def record_route_call(
        self,
        *,
        route_key: str,
        provider: str,
        model: str,
        success: bool,
        latency_ms: int,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        error: str | None = None,
        remote_request_limit: int | None = None,
        remote_requests_remaining: int | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_route_call_sync,
            route_key,
            provider,
            model,
            success,
            latency_ms,
            input_tokens or 0,
            output_tokens or 0,
            error,
            remote_request_limit,
            remote_requests_remaining,
        )

    def _record_route_call_sync(
        self,
        route_key: str,
        provider: str,
        model: str,
        success: bool,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        error: str | None,
        remote_request_limit: int | None,
        remote_requests_remaining: int | None,
    ) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO route_stats(
                    route_key,
                    provider,
                    model,
                    total_calls,
                    successful_calls,
                    failed_calls,
                    total_latency_ms,
                    total_input_tokens,
                    total_output_tokens,
                    last_error,
                    remote_request_limit,
                    remote_requests_remaining,
                    updated_at
                )
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(route_key) DO UPDATE SET
                    provider = excluded.provider,
                    model = excluded.model,
                    total_calls = total_calls + 1,
                    successful_calls = successful_calls + excluded.successful_calls,
                    failed_calls = failed_calls + excluded.failed_calls,
                    total_latency_ms = total_latency_ms + excluded.total_latency_ms,
                    total_input_tokens = total_input_tokens + excluded.total_input_tokens,
                    total_output_tokens = total_output_tokens + excluded.total_output_tokens,
                    last_error = excluded.last_error,
                    remote_request_limit = COALESCE(
                        excluded.remote_request_limit,
                        remote_request_limit
                    ),
                    remote_requests_remaining = COALESCE(
                        excluded.remote_requests_remaining,
                        remote_requests_remaining
                    ),
                    updated_at = excluded.updated_at
                """,
                (
                    route_key,
                    provider,
                    model,
                    1 if success else 0,
                    0 if success else 1,
                    latency_ms,
                    input_tokens,
                    output_tokens,
                    error,
                    remote_request_limit,
                    remote_requests_remaining,
                    now,
                ),
            )
            connection.commit()

    async def route_stats(self) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._route_stats_sync)

    async def record_verified_task_route(
        self,
        *,
        task_signature: str,
        route_key: str,
        success: bool,
        latency_ms: int = 0,
        output_tokens: int = 0,
    ) -> None:
        if not task_signature or not route_key:
            return
        await asyncio.to_thread(
            self._record_verified_task_route_sync,
            task_signature,
            route_key,
            success,
            latency_ms,
            output_tokens,
        )

    def _record_verified_task_route_sync(
        self,
        task_signature: str,
        route_key: str,
        success: bool,
        latency_ms: int,
        output_tokens: int,
    ) -> None:
        now = time.time()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO verified_task_route_stats(
                    task_signature, route_key, verified_successes,
                    verified_failures, total_latency_ms,
                    total_output_tokens, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_signature, route_key) DO UPDATE SET
                    verified_successes=verified_successes
                        + excluded.verified_successes,
                    verified_failures=verified_failures
                        + excluded.verified_failures,
                    total_latency_ms=total_latency_ms
                        + excluded.total_latency_ms,
                    total_output_tokens=total_output_tokens
                        + excluded.total_output_tokens,
                    updated_at=excluded.updated_at
                """,
                (
                    task_signature,
                    route_key,
                    int(success),
                    int(not success),
                    max(0, int(latency_ms)),
                    max(0, int(output_tokens)),
                    now,
                ),
            )
            connection.commit()

    async def verified_task_route_stats(
        self,
        task_signature: str,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(
            self._verified_task_route_stats_sync,
            task_signature,
        )

    def _verified_task_route_stats_sync(
        self,
        task_signature: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM verified_task_route_stats
                    WHERE task_signature=? ORDER BY route_key
                    """,
                    (task_signature,),
                ).fetchall()
            ]

    def _route_stats_sync(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM route_stats ORDER BY route_key"
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            total_calls = int(item["total_calls"])
            item["average_latency_ms"] = (
                round(int(item["total_latency_ms"]) / total_calls)
                if total_calls
                else 0
            )
            item["success_rate"] = (
                int(item["successful_calls"]) / total_calls
                if total_calls
                else None
            )
            result.append(item)
        return result
