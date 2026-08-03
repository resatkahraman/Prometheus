from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from app.memory.attention import AttentionCard
from app.memory.indexing import (
    IndexedDependency,
    IndexedSymbol,
    index_source,
    named_imports,
)


_NUMBERED_LINE = re.compile(r"^\s*\d+:\s?")
_CODE_OUTLINE = re.compile(
    r"^\s*(?:"
    r"from\s+\S+\s+import\s+|import\s+|export\s+|"
    r"(?:async\s+)?def\s+\w+|class\s+\w+|"
    r"(?:async\s+)?function\s+\w+|"
    r"(?:const|let|var)\s+\w+\s*=|"
    r"interface\s+\w+|type\s+\w+"
    r")"
)
_MARKUP_OUTLINE = re.compile(
    r"^\s*(?:#{1,4}\s+|<(?:title|h1|h2|form|main|section)\b)",
    re.IGNORECASE,
)
_CSS_SELECTOR = re.compile(r"^\s*[.#][a-zA-Z_-][^{}]{0,100}\s*\{")
_RETRIEVAL_TOKEN = re.compile(r"[a-zA-Z0-9_.$/-]+")


@dataclass(frozen=True)
class FileMemory:
    path: str
    sha256: str
    size_bytes: int
    outline: str
    state: str


@dataclass(frozen=True)
class Hypothesis:
    id: str
    claim: str
    rationale: str
    task_scope: str | None
    status: str
    created_at: str
    updated_at: str


def _plain_text(content: str) -> str:
    return "\n".join(
        _NUMBERED_LINE.sub("", line)
        for line in content.splitlines()
    )


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = max(1, int(limit * 0.7))
    tail = max(1, limit - head - 35)
    return (
        text[:head]
        + "\n... project memory clipped ...\n"
        + text[-tail:]
    )


def build_outline(path: str, content: str, *, max_chars: int = 1_600) -> str:
    """Create a deterministic, local outline without sending data to a model."""

    plain = _plain_text(content)
    suffix = Path(path).suffix.casefold()
    selected: list[str] = []

    if suffix == ".json":
        try:
            payload = json.loads(plain)
        except (json.JSONDecodeError, TypeError):
            payload = None
        if isinstance(payload, dict):
            for key in (
                "name",
                "version",
                "type",
                "scripts",
                "dependencies",
                "devDependencies",
            ):
                if key in payload:
                    value = json.dumps(
                        payload[key],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    selected.append(f"{key}: {value}")

    if not selected:
        for line in plain.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if (
                _CODE_OUTLINE.search(line)
                or _MARKUP_OUTLINE.search(line)
                or _CSS_SELECTOR.search(line)
            ):
                selected.append(stripped[:240])
            if len(selected) >= 24:
                break

    if not selected:
        selected = [
            line.strip()[:240]
            for line in plain.splitlines()
            if line.strip()
        ][:8]

    outline = "\n".join(selected)
    return _clip(outline or "(empty file)", max_chars)


class ProjectMemoryStore:
    """Small local project memory backed by Python's built-in SQLite module.

    Only hashes, deterministic outlines and context metrics are stored. Full
    source files and prompts are deliberately not persisted in this database.
    """

    def __init__(self, path: Path, *, enabled: bool = True) -> None:
        self.path = path.expanduser().resolve()
        self.enabled = enabled
        self._initialized = False
        self._lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_sync(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS file_memory (
                    path TEXT PRIMARY KEY,
                    sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    outline TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS context_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    task_fingerprint TEXT NOT NULL,
                    context_chars INTEGER NOT NULL,
                    full_file_count INTEGER NOT NULL,
                    summarized_file_count INTEGER NOT NULL,
                    selected_paths_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS context_compiler_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    task_fingerprint TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    cache_hit INTEGER NOT NULL,
                    baseline_chars INTEGER NOT NULL,
                    candidate_chars INTEGER NOT NULL,
                    baseline_estimated_tokens INTEGER NOT NULL,
                    candidate_estimated_tokens INTEGER NOT NULL,
                    saved_chars INTEGER NOT NULL,
                    eligible INTEGER NOT NULL,
                    fallback_required INTEGER NOT NULL,
                    selected_segments_json TEXT NOT NULL,
                    omitted_segments_json TEXT NOT NULL,
                    deduplicated_segments_json TEXT NOT NULL,
                    source_hashes_json TEXT NOT NULL,
                    retrieved_card_ids_json TEXT NOT NULL,
                    missing_evidence_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS symbols (
                    path TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    PRIMARY KEY(path, name, kind, line)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dependencies (
                    source_path TEXT NOT NULL,
                    target_ref TEXT NOT NULL,
                    resolved_path TEXT,
                    kind TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL,
                    PRIMARY KEY(source_path, target_ref, kind)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS evidence_cards (
                    id TEXT PRIMARY KEY,
                    claim TEXT NOT NULL,
                    source_path TEXT,
                    source_sha256 TEXT,
                    evidence_type TEXT NOT NULL,
                    evidence_ref TEXT,
                    state TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS hypotheses (
                    id TEXT PRIMARY KEY,
                    claim TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    task_scope TEXT,
                    status TEXT NOT NULL,
                    promotion_evidence_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_symbols_name "
                "ON symbols(name)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_dependencies_target "
                "ON dependencies(resolved_path)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_evidence_source "
                "ON evidence_cards(source_path, state)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_context_compiler_cache "
                "ON context_compiler_runs(cache_key)"
            )
            connection.commit()

    async def initialize(self) -> None:
        if not self.enabled or self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._initialize_sync)
            self._initialized = True

    def _remember_file_sync(
        self,
        *,
        path: str,
        sha256: str,
        size_bytes: int,
        outline: str,
        symbols: list[IndexedSymbol],
        dependencies: list[IndexedDependency],
    ) -> FileMemory:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            previous = connection.execute(
                "SELECT sha256 FROM file_memory WHERE path = ?",
                (path,),
            ).fetchone()
            state = (
                "new"
                if previous is None
                else "unchanged"
                if str(previous["sha256"]) == sha256
                else "changed"
            )
            connection.execute(
                """
                INSERT INTO file_memory(
                    path, sha256, size_bytes, outline, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    sha256=excluded.sha256,
                    size_bytes=excluded.size_bytes,
                    outline=excluded.outline,
                    updated_at=excluded.updated_at
                """,
                (path, sha256, size_bytes, outline, now),
            )
            connection.execute(
                """
                UPDATE evidence_cards
                SET state='stale', updated_at=?
                WHERE source_path=?
                  AND source_sha256 IS NOT NULL
                  AND source_sha256<>?
                """,
                (now, path, sha256),
            )
            connection.execute("DELETE FROM symbols WHERE path=?", (path,))
            connection.execute(
                "DELETE FROM dependencies WHERE source_path=?",
                (path,),
            )
            connection.executemany(
                """
                INSERT INTO symbols(
                    path, name, kind, line, source_sha256
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                list(
                    dict.fromkeys(
                        (
                            path,
                            item.name,
                            item.kind,
                            item.line,
                            sha256,
                        )
                        for item in symbols
                    )
                ),
            )
            connection.executemany(
                """
                INSERT INTO dependencies(
                    source_path,
                    target_ref,
                    resolved_path,
                    kind,
                    source_sha256
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                list(
                    dict.fromkeys(
                        (
                            path,
                            item.reference,
                            item.resolved_path,
                            item.kind,
                            sha256,
                        )
                        for item in dependencies
                    )
                ),
            )
            evidence_rows: list[tuple] = [
                (
                    hashlib.sha256(
                        f"file:{path}".encode("utf-8")
                    ).hexdigest(),
                    f"{path} exists and is indexed at sha256 {sha256}.",
                    path,
                    sha256,
                    "file",
                    path,
                    "verified",
                    1.0,
                    now,
                )
            ]
            evidence_rows.extend(
                (
                    hashlib.sha256(
                        (
                            f"symbol:{path}:{item.name}:"
                            f"{item.kind}:{item.line}"
                        ).encode("utf-8")
                    ).hexdigest(),
                    (
                        f"{path} defines {item.kind} "
                        f"{item.name} at line {item.line}."
                    ),
                    path,
                    sha256,
                    "symbol",
                    f"{path}:{item.line}",
                    "verified",
                    1.0,
                    now,
                )
                for item in symbols
            )
            evidence_rows.extend(
                (
                    hashlib.sha256(
                        (
                            f"dependency:{path}:{item.reference}:"
                            f"{item.kind}"
                        ).encode("utf-8")
                    ).hexdigest(),
                    (
                        f"{path} depends on {item.reference}"
                        + (
                            f" resolved as {item.resolved_path}."
                            if item.resolved_path
                            else "."
                        )
                    ),
                    path,
                    sha256,
                    "dependency",
                    item.resolved_path or item.reference,
                    "verified",
                    1.0,
                    now,
                )
                for item in dependencies
            )
            connection.executemany(
                """
                INSERT INTO evidence_cards(
                    id,
                    claim,
                    source_path,
                    source_sha256,
                    evidence_type,
                    evidence_ref,
                    state,
                    confidence,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    claim=excluded.claim,
                    source_sha256=excluded.source_sha256,
                    evidence_ref=excluded.evidence_ref,
                    state='verified',
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at
                """,
                evidence_rows,
            )
            connection.commit()
        return FileMemory(
            path=path,
            sha256=sha256,
            size_bytes=size_bytes,
            outline=outline,
            state=state,
        )

    async def remember_file(self, *, path: str, content: str) -> FileMemory:
        plain = _plain_text(content)
        encoded = plain.encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        outline = build_outline(path, content)
        symbols, dependencies = index_source(path, content)
        if not self.enabled:
            return FileMemory(
                path=path,
                sha256=digest,
                size_bytes=len(encoded),
                outline=outline,
                state="untracked",
            )

        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(
                self._remember_file_sync,
                path=path,
                sha256=digest,
                size_bytes=len(encoded),
                outline=outline,
                symbols=symbols,
                dependencies=dependencies,
            )

    def _context_cards_sync(
        self,
        *,
        paths: list[str],
        include_hypotheses: bool,
        limit: int,
    ) -> list[AttentionCard]:
        with self._connect() as connection:
            parameters: list = []
            where = "state='verified'"
            if paths:
                placeholders = ",".join("?" for _ in paths)
                where += f" AND (source_path IN ({placeholders}) OR source_path IS NULL)"
                parameters.extend(paths)
            rows = connection.execute(
                f"""
                SELECT id, claim, source_path, evidence_type, state, confidence
                FROM evidence_cards
                WHERE {where}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (*parameters, limit),
            ).fetchall()
            cards = [
                AttentionCard(
                    id=str(row["id"]),
                    claim=str(row["claim"]),
                    source_path=(
                        str(row["source_path"])
                        if row["source_path"] is not None
                        else None
                    ),
                    evidence_type=str(row["evidence_type"]),
                    state=str(row["state"]),
                    confidence=float(row["confidence"]),
                )
                for row in rows
            ]
            if include_hypotheses and len(cards) < limit:
                hypotheses = connection.execute(
                    """
                    SELECT id, claim
                    FROM hypotheses
                    WHERE status='hypothesis'
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (limit - len(cards),),
                ).fetchall()
                cards.extend(
                    AttentionCard(
                        id=f"hypothesis:{row['id']}",
                        claim=str(row["claim"]),
                        source_path=None,
                        evidence_type="hypothesis",
                        state="hypothesis",
                        confidence=0.25,
                    )
                    for row in hypotheses
                )
        return cards

    async def context_cards(
        self,
        *,
        paths: list[str],
        include_hypotheses: bool = False,
        limit: int = 120,
    ) -> list[AttentionCard]:
        if not self.enabled:
            return []
        await self.initialize()
        return await asyncio.to_thread(
            self._context_cards_sync,
            paths=paths,
            include_hypotheses=include_hypotheses,
            limit=limit,
        )

    @staticmethod
    def _retrieval_tokens(value: str) -> set[str]:
        return {
            token.casefold()
            for token in _RETRIEVAL_TOKEN.findall(value)
            if len(token) > 1
        }

    def _retrieve_context_cards_sync(
        self,
        *,
        query: str,
        seed_paths: list[str],
        include_hypotheses: bool,
        limit: int,
        scan_limit: int,
    ) -> list[AttentionCard]:
        query_tokens = self._retrieval_tokens(
            f"{query} {' '.join(seed_paths)}"
        )
        seed_set = {
            item.replace("\\", "/").casefold()
            for item in seed_paths
            if item.strip()
        }
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, claim, source_path, evidence_type, state, confidence
                FROM evidence_cards
                WHERE state='verified'
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (scan_limit,),
            ).fetchall()
            hypotheses = []
            if include_hypotheses:
                hypotheses = connection.execute(
                    """
                    SELECT id, claim
                    FROM hypotheses
                    WHERE status='hypothesis'
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (min(scan_limit, 200),),
                ).fetchall()

        ranked: list[tuple[float, str, AttentionCard]] = []
        for row in rows:
            source_path = (
                str(row["source_path"])
                if row["source_path"] is not None
                else None
            )
            card = AttentionCard(
                id=str(row["id"]),
                claim=str(row["claim"]),
                source_path=source_path,
                evidence_type=str(row["evidence_type"]),
                state=str(row["state"]),
                confidence=float(row["confidence"]),
            )
            card_tokens = self._retrieval_tokens(
                f"{card.claim} {source_path or ''}"
            )
            overlap = len(query_tokens & card_tokens)
            score = overlap * 12.0 + card.confidence * 5.0
            if (
                source_path
                and source_path.replace("\\", "/").casefold() in seed_set
            ):
                score += 35.0
            if card.evidence_type in {
                "test",
                "tool_result",
                "user_decision",
            }:
                score += 12.0
            if overlap or score >= 30.0:
                ranked.append((score, card.id, card))

        for row in hypotheses:
            card = AttentionCard(
                id=f"hypothesis:{row['id']}",
                claim=str(row["claim"]),
                source_path=None,
                evidence_type="hypothesis",
                state="hypothesis",
                confidence=0.25,
            )
            overlap = len(
                query_tokens & self._retrieval_tokens(card.claim)
            )
            if overlap:
                ranked.append((overlap * 6.0, card.id, card))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in ranked[:limit]]

    async def retrieve_context_cards(
        self,
        *,
        query: str,
        seed_paths: list[str],
        include_hypotheses: bool = False,
        limit: int = 32,
        scan_limit: int = 1_000,
    ) -> list[AttentionCard]:
        """Local RAG over verified evidence with path and lexical ranking."""

        if not self.enabled:
            return []
        await self.initialize()
        return await asyncio.to_thread(
            self._retrieve_context_cards_sync,
            query=query,
            seed_paths=seed_paths,
            include_hypotheses=include_hypotheses,
            limit=limit,
            scan_limit=scan_limit,
        )

    def _related_paths_sync(self, path: str) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT resolved_path AS path
                FROM dependencies
                WHERE source_path=? AND resolved_path IS NOT NULL
                UNION
                SELECT source_path AS path
                FROM dependencies
                WHERE resolved_path=?
                """,
                (path, path),
            ).fetchall()
        return [str(row["path"]) for row in rows if row["path"]]

    async def related_paths(self, path: str) -> list[str]:
        if not self.enabled:
            return []
        await self.initialize()
        return await asyncio.to_thread(self._related_paths_sync, path)

    def _resolve_symbols_sync(self, names: list[str]) -> list[str]:
        normalized = [item.casefold() for item in names if item.strip()]
        if not normalized:
            return []
        placeholders = ",".join("?" for _ in normalized)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT path
                FROM symbols
                WHERE lower(name) IN ({placeholders})
                ORDER BY path
                """,
                normalized,
            ).fetchall()
        return [str(row["path"]) for row in rows]

    async def resolve_symbols(self, names: list[str]) -> list[str]:
        if not self.enabled:
            return []
        await self.initialize()
        return await asyncio.to_thread(
            self._resolve_symbols_sync,
            names,
        )

    def _validate_source_evidence_sync(
        self,
        *,
        path: str,
        content: str,
        allowed_missing_paths: list[str] | None = None,
    ) -> dict:
        imports = named_imports(path, content)
        issues: list[str] = []
        missing_context: list[str] = []
        pending_imports: list[dict[str, str]] = []
        allowed_missing = {
            item.replace("\\", "/").removeprefix("./")
            for item in (allowed_missing_paths or [])
            if item.strip()
        }
        with self._connect() as connection:
            for item in imports:
                if item.resolved_path is None:
                    continue
                indexed = connection.execute(
                    "SELECT 1 FROM file_memory WHERE path=?",
                    (item.resolved_path,),
                ).fetchone()
                if indexed is None:
                    if item.resolved_path in allowed_missing:
                        pending_imports.append(
                            {
                                "name": item.name,
                                "reference": item.reference,
                                "resolved_path": item.resolved_path,
                            }
                        )
                        continue
                    missing_context.append(item.resolved_path)
                    continue
                symbol = connection.execute(
                    """
                    SELECT 1
                    FROM symbols
                    WHERE path=? AND name=?
                    """,
                    (item.resolved_path, item.name),
                ).fetchone()
                if symbol is None:
                    available = [
                        str(row["name"])
                        for row in connection.execute(
                            """
                            SELECT DISTINCT name
                            FROM symbols
                            WHERE path=?
                            ORDER BY name
                            """,
                            (item.resolved_path,),
                        ).fetchall()
                    ]
                    issues.append(
                        f"{path} imports '{item.name}' from "
                        f"{item.resolved_path}, but verified exports/symbols "
                        f"are: {available or ['none']}."
                    )
        return {
            "valid": not issues and not missing_context,
            "issues": issues,
            "missing_context_paths": list(
                dict.fromkeys(missing_context)
            ),
            "pending_imports": pending_imports,
            "checked_imports": [
                {
                    "name": item.name,
                    "reference": item.reference,
                    "resolved_path": item.resolved_path,
                }
                for item in imports
            ],
        }

    async def validate_source_evidence(
        self,
        *,
        path: str,
        content: str,
        allowed_missing_paths: list[str] | None = None,
    ) -> dict:
        if not self.enabled:
            return {
                "valid": True,
                "issues": [],
                "missing_context_paths": [],
                "pending_imports": [],
                "checked_imports": [],
                "memory_disabled": True,
            }
        await self.initialize()
        return await asyncio.to_thread(
            self._validate_source_evidence_sync,
            path=path,
            content=content,
            allowed_missing_paths=allowed_missing_paths,
        )

    def _record_evidence_sync(
        self,
        *,
        claim: str,
        evidence_type: str,
        evidence_ref: str,
        source_path: str | None,
        source_sha256: str | None,
        confidence: float,
    ) -> str:
        identifier = hashlib.sha256(
            (
                f"{evidence_type}:{evidence_ref}:"
                f"{source_path or ''}:{claim}"
            ).encode("utf-8")
        ).hexdigest()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO evidence_cards(
                    id, claim, source_path, source_sha256,
                    evidence_type, evidence_ref, state,
                    confidence, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'verified', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    claim=excluded.claim,
                    source_sha256=excluded.source_sha256,
                    state='verified',
                    confidence=excluded.confidence,
                    updated_at=excluded.updated_at
                """,
                (
                    identifier,
                    claim,
                    source_path,
                    source_sha256,
                    evidence_type,
                    evidence_ref,
                    confidence,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        return identifier

    async def record_evidence(
        self,
        *,
        claim: str,
        evidence_type: str,
        evidence_ref: str,
        source_path: str | None = None,
        source_sha256: str | None = None,
        confidence: float = 1.0,
    ) -> str:
        if not self.enabled:
            return ""
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(
                self._record_evidence_sync,
                claim=claim,
                evidence_type=evidence_type,
                evidence_ref=evidence_ref,
                source_path=source_path,
                source_sha256=source_sha256,
                confidence=confidence,
            )

    def _add_hypothesis_sync(
        self,
        *,
        claim: str,
        rationale: str,
        task_scope: str | None,
    ) -> Hypothesis:
        identifier = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO hypotheses(
                    id, claim, rationale, task_scope,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'hypothesis', ?, ?)
                """,
                (identifier, claim, rationale, task_scope, now, now),
            )
            connection.commit()
        return Hypothesis(
            id=identifier,
            claim=claim,
            rationale=rationale,
            task_scope=task_scope,
            status="hypothesis",
            created_at=now,
            updated_at=now,
        )

    async def add_hypothesis(
        self,
        *,
        claim: str,
        rationale: str,
        task_scope: str | None = None,
    ) -> Hypothesis:
        if not claim.strip() or not rationale.strip():
            raise ValueError("Hypothesis claim and rationale are required.")
        if not self.enabled:
            raise ValueError("Project memory is disabled.")
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(
                self._add_hypothesis_sync,
                claim=claim.strip(),
                rationale=rationale.strip(),
                task_scope=task_scope,
            )

    def _promote_hypothesis_sync(
        self,
        *,
        hypothesis_id: str,
        evidence_ids: list[str],
    ) -> Hypothesis:
        with self._connect() as connection:
            hypothesis = connection.execute(
                "SELECT * FROM hypotheses WHERE id=?",
                (hypothesis_id,),
            ).fetchone()
            if hypothesis is None:
                raise KeyError("Hypothesis not found.")
            if not evidence_ids:
                raise ValueError("Promotion requires verified evidence.")
            placeholders = ",".join("?" for _ in evidence_ids)
            rows = connection.execute(
                f"""
                SELECT id, evidence_type, state
                FROM evidence_cards
                WHERE id IN ({placeholders})
                """,
                evidence_ids,
            ).fetchall()
            if len(rows) != len(set(evidence_ids)) or any(
                row["state"] != "verified" for row in rows
            ):
                raise ValueError(
                    "Promotion evidence must exist and be verified."
                )
            if not any(
                row["evidence_type"]
                in {"test", "tool_result", "user_decision"}
                for row in rows
            ):
                raise ValueError(
                    "Promotion requires test, tool or user-decision evidence."
                )
            now = datetime.now(timezone.utc).isoformat()
            connection.execute(
                """
                UPDATE hypotheses
                SET status='promoted',
                    promotion_evidence_json=?,
                    updated_at=?
                WHERE id=?
                """,
                (json.dumps(evidence_ids), now, hypothesis_id),
            )
            promoted_id = hashlib.sha256(
                f"promoted-hypothesis:{hypothesis_id}".encode("utf-8")
            ).hexdigest()
            connection.execute(
                """
                INSERT INTO evidence_cards(
                    id, claim, source_path, source_sha256,
                    evidence_type, evidence_ref, state,
                    confidence, updated_at
                )
                VALUES (?, ?, NULL, NULL, 'hypothesis_promoted', ?,
                        'verified', 1.0, ?)
                ON CONFLICT(id) DO UPDATE SET
                    claim=excluded.claim,
                    evidence_ref=excluded.evidence_ref,
                    state='verified',
                    confidence=1.0,
                    updated_at=excluded.updated_at
                """,
                (
                    promoted_id,
                    str(hypothesis["claim"]),
                    json.dumps(evidence_ids),
                    now,
                ),
            )
            connection.commit()
        return Hypothesis(
            id=hypothesis_id,
            claim=str(hypothesis["claim"]),
            rationale=str(hypothesis["rationale"]),
            task_scope=(
                str(hypothesis["task_scope"])
                if hypothesis["task_scope"] is not None
                else None
            ),
            status="promoted",
            created_at=str(hypothesis["created_at"]),
            updated_at=now,
        )

    async def promote_hypothesis(
        self,
        *,
        hypothesis_id: str,
        evidence_ids: list[str],
    ) -> Hypothesis:
        if not self.enabled:
            raise ValueError("Project memory is disabled.")
        await self.initialize()
        async with self._lock:
            return await asyncio.to_thread(
                self._promote_hypothesis_sync,
                hypothesis_id=hypothesis_id,
                evidence_ids=evidence_ids,
            )

    def _record_context_sync(
        self,
        *,
        source: str,
        task_fingerprint: str,
        context_chars: int,
        full_file_count: int,
        summarized_file_count: int,
        selected_paths: list[str],
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO context_runs(
                    source,
                    task_fingerprint,
                    context_chars,
                    full_file_count,
                    summarized_file_count,
                    selected_paths_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    task_fingerprint,
                    context_chars,
                    full_file_count,
                    summarized_file_count,
                    json.dumps(selected_paths, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()

    async def record_context(
        self,
        *,
        source: str,
        task_text: str,
        context_chars: int,
        full_file_count: int,
        summarized_file_count: int,
        selected_paths: list[str],
    ) -> None:
        if not self.enabled:
            return
        await self.initialize()
        fingerprint = hashlib.sha256(
            task_text.encode("utf-8")
        ).hexdigest()
        async with self._lock:
            await asyncio.to_thread(
                self._record_context_sync,
                source=source,
                task_fingerprint=fingerprint,
                context_chars=context_chars,
                full_file_count=full_file_count,
                summarized_file_count=summarized_file_count,
                selected_paths=selected_paths,
            )

    def _latest_context_sync(self, source: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM context_runs
                WHERE source = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source,),
            ).fetchone()
        return dict(row) if row is not None else None

    async def latest_context(self, source: str) -> dict | None:
        if not self.enabled:
            return None
        await self.initialize()
        return await asyncio.to_thread(
            self._latest_context_sync,
            source,
        )

    def _record_context_compilation_sync(
        self,
        *,
        source: str,
        task_fingerprint: str,
        mode: str,
        cache_key: str,
        baseline_chars: int,
        candidate_chars: int,
        baseline_estimated_tokens: int,
        candidate_estimated_tokens: int,
        saved_chars: int,
        eligible: bool,
        fallback_required: bool,
        selected_segment_ids: list[str],
        omitted_segment_ids: list[str],
        deduplicated_segment_ids: list[str],
        source_hashes: dict[str, str],
        retrieved_card_ids: list[str],
        missing_evidence: list[str],
    ) -> bool:
        with self._connect() as connection:
            previous = connection.execute(
                """
                SELECT 1
                FROM context_compiler_runs
                WHERE cache_key=?
                LIMIT 1
                """,
                (cache_key,),
            ).fetchone()
            cache_hit = previous is not None
            connection.execute(
                """
                INSERT INTO context_compiler_runs(
                    source,
                    task_fingerprint,
                    mode,
                    cache_key,
                    cache_hit,
                    baseline_chars,
                    candidate_chars,
                    baseline_estimated_tokens,
                    candidate_estimated_tokens,
                    saved_chars,
                    eligible,
                    fallback_required,
                    selected_segments_json,
                    omitted_segments_json,
                    deduplicated_segments_json,
                    source_hashes_json,
                    retrieved_card_ids_json,
                    missing_evidence_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    task_fingerprint,
                    mode,
                    cache_key,
                    int(cache_hit),
                    baseline_chars,
                    candidate_chars,
                    baseline_estimated_tokens,
                    candidate_estimated_tokens,
                    saved_chars,
                    int(eligible),
                    int(fallback_required),
                    json.dumps(selected_segment_ids, ensure_ascii=False),
                    json.dumps(omitted_segment_ids, ensure_ascii=False),
                    json.dumps(deduplicated_segment_ids, ensure_ascii=False),
                    json.dumps(
                        source_hashes,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    json.dumps(retrieved_card_ids, ensure_ascii=False),
                    json.dumps(missing_evidence, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        return cache_hit

    async def record_context_compilation(
        self,
        *,
        source: str,
        task_text: str,
        mode: str,
        cache_key: str,
        baseline_chars: int,
        candidate_chars: int,
        baseline_estimated_tokens: int,
        candidate_estimated_tokens: int,
        saved_chars: int,
        eligible: bool,
        fallback_required: bool,
        selected_segment_ids: list[str],
        omitted_segment_ids: list[str],
        deduplicated_segment_ids: list[str],
        source_hashes: dict[str, str],
        retrieved_card_ids: list[str],
        missing_evidence: list[str],
    ) -> bool:
        if not self.enabled:
            return False
        await self.initialize()
        task_fingerprint = hashlib.sha256(
            task_text.encode("utf-8")
        ).hexdigest()
        async with self._lock:
            return await asyncio.to_thread(
                self._record_context_compilation_sync,
                source=source,
                task_fingerprint=task_fingerprint,
                mode=mode,
                cache_key=cache_key,
                baseline_chars=baseline_chars,
                candidate_chars=candidate_chars,
                baseline_estimated_tokens=baseline_estimated_tokens,
                candidate_estimated_tokens=candidate_estimated_tokens,
                saved_chars=saved_chars,
                eligible=eligible,
                fallback_required=fallback_required,
                selected_segment_ids=selected_segment_ids,
                omitted_segment_ids=omitted_segment_ids,
                deduplicated_segment_ids=deduplicated_segment_ids,
                source_hashes=source_hashes,
                retrieved_card_ids=retrieved_card_ids,
                missing_evidence=missing_evidence,
            )

    def _latest_context_compilation_sync(
        self,
        source: str,
    ) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM context_compiler_runs
                WHERE source=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (source,),
            ).fetchone()
        return dict(row) if row is not None else None

    async def latest_context_compilation(
        self,
        source: str,
    ) -> dict | None:
        if not self.enabled:
            return None
        await self.initialize()
        return await asyncio.to_thread(
            self._latest_context_compilation_sync,
            source,
        )

    def _context_compiler_summary_sync(self) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    COUNT(*) AS runs,
                    COALESCE(SUM(cache_hit), 0) AS cache_hits,
                    COALESCE(SUM(eligible), 0) AS eligible_runs,
                    COALESCE(SUM(
                        CASE
                            WHEN eligible=1
                             AND candidate_chars < baseline_chars
                            THEN 1
                            ELSE 0
                        END
                    ), 0) AS beneficial_runs,
                    COALESCE(SUM(fallback_required), 0) AS fallback_runs,
                    COALESCE(SUM(baseline_chars), 0) AS baseline_chars,
                    COALESCE(SUM(candidate_chars), 0) AS candidate_chars,
                    COALESCE(SUM(baseline_estimated_tokens), 0)
                        AS baseline_estimated_tokens,
                    COALESCE(SUM(candidate_estimated_tokens), 0)
                        AS candidate_estimated_tokens,
                    COALESCE(SUM(
                        CASE
                            WHEN eligible=1
                             AND candidate_chars < baseline_chars
                            THEN saved_chars
                            ELSE 0
                        END
                    ), 0) AS eligible_saved_chars,
                    COALESCE(SUM(
                        CASE
                            WHEN eligible=1
                             AND candidate_chars < baseline_chars
                            THEN baseline_estimated_tokens
                                 - candidate_estimated_tokens
                            ELSE 0
                        END
                    ), 0) AS eligible_saved_estimated_tokens
                FROM context_compiler_runs
                """
            ).fetchone()
            mode_row = connection.execute(
                """
                SELECT mode
                FROM context_compiler_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        summary = dict(row)
        runs = int(summary["runs"])
        baseline_chars = int(summary["baseline_chars"])
        eligible_saved_chars = int(summary["eligible_saved_chars"])
        summary["cache_hit_rate"] = (
            round(int(summary["cache_hits"]) / runs, 4)
            if runs
            else 0.0
        )
        summary["eligible_rate"] = (
            round(int(summary["eligible_runs"]) / runs, 4)
            if runs
            else 0.0
        )
        summary["beneficial_rate"] = (
            round(int(summary["beneficial_runs"]) / runs, 4)
            if runs
            else 0.0
        )
        summary["bypassed_runs"] = (
            runs - int(summary["beneficial_runs"])
        )
        summary["eligible_projected_savings_ratio"] = (
            round(eligible_saved_chars / baseline_chars, 4)
            if baseline_chars
            else 0.0
        )
        summary["mode"] = (
            str(mode_row["mode"]) if mode_row is not None else "off"
        )
        return summary

    async def context_compiler_summary(self) -> dict:
        if not self.enabled:
            return {
                "mode": "off",
                "runs": 0,
                "cache_hits": 0,
                "eligible_runs": 0,
                "beneficial_runs": 0,
                "fallback_runs": 0,
                "baseline_chars": 0,
                "candidate_chars": 0,
                "baseline_estimated_tokens": 0,
                "candidate_estimated_tokens": 0,
                "eligible_saved_chars": 0,
                "eligible_saved_estimated_tokens": 0,
                "cache_hit_rate": 0.0,
                "eligible_rate": 0.0,
                "beneficial_rate": 0.0,
                "bypassed_runs": 0,
                "eligible_projected_savings_ratio": 0.0,
            }
        await self.initialize()
        return await asyncio.to_thread(
            self._context_compiler_summary_sync
        )
