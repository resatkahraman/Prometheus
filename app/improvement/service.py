from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from app.core.config import Settings
from app.improvement.embedding import OllamaEmbeddingClient
from app.improvement.models import RecallCapsule
from app.improvement.store import ImprovementStore
from app.memory.project import build_outline
from app.workspace.policy import WorkspacePolicy


_TOKEN = re.compile(r"[a-zA-Z0-9_./$-]+")


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN.findall(text) if len(token) > 1}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


class ImprovementService:
    """PEEK-like orientation cache plus verified experience kernel."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        path = settings.improvement_database_path
        if not path.is_absolute():
            path = settings.workspace_root / path
        self.store = ImprovementStore(
            Path(path),
            enabled=settings.experience_kernel_enabled,
        )
        root = settings.workspace_root.expanduser().resolve()
        self.workspace = WorkspacePolicy(
            root=root,
            max_file_bytes=settings.workspace_max_file_bytes,
            max_search_results=settings.workspace_max_search_results,
        )
        self.project_key = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:20]
        self.embedding = (
            OllamaEmbeddingClient(
                base_url=settings.ollama_base_url,
                model=settings.ollama_embedding_model,
                timeout_seconds=settings.embedding_timeout_seconds,
            )
            if settings.local_embedding_enabled
            else None
        )

    @staticmethod
    def task_signature(
        *,
        title: str,
        verification: str = "",
        paths: list[str] | None = None,
    ) -> str:
        suffixes = sorted(
            {
                Path(path).suffix.casefold() or "<none>"
                for path in (paths or [])
            }
        )
        title_tokens = sorted(_tokens(title))[:12]
        verify_head = (verification.strip().split() or ["none"])[0].casefold()
        material = "|".join([",".join(suffixes), verify_head, *title_tokens])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]

    async def remember_orientation(
        self,
        *,
        path: str,
        source_sha256: str,
        outline: str,
        relations: list[str] | None = None,
    ) -> list[str]:
        ids: list[str] = []
        entries = [("outline", outline[:2_000])]
        if relations:
            entries.append(("relations", "related: " + ", ".join(sorted(relations)[:40])))
        for kind, content in entries:
            if not content.strip():
                continue
            ids.append(
                await self.store.upsert_orientation(
                    project_key=self.project_key,
                    path=path,
                    source_sha256=source_sha256,
                    kind=kind,
                    content=content,
                )
            )
        return [entry_id for entry_id in ids if entry_id]

    async def _query_embedding(self, text: str) -> list[float] | None:
        if self.embedding is None:
            return None
        try:
            values = await self.embedding.embed([text[:4_000]])
            return values[0] if values else None
        except Exception:
            return None

    async def recall(
        self,
        *,
        query: str,
        target_path: str | None = None,
        max_chars: int | None = None,
    ) -> RecallCapsule:
        budget = max_chars or self.settings.orientation_cache_budget_chars
        signature = self.task_signature(
            title=query,
            paths=[target_path] if target_path else [],
        )
        orientations, strategies = await self.store.recall_rows(
            project_key=self.project_key,
            limit=self.settings.orientation_cache_scan_limit,
        )
        active_candidates = await self.store.active_candidates(
            project_key=self.project_key,
        )
        query_tokens = _tokens(f"{query} {target_path or ''}")
        query_embedding = None
        if self.embedding is not None:
            pending = [
                row
                for row in sorted(
                    orientations,
                    key=lambda item: (
                        len(
                            query_tokens
                            & _tokens(
                                f"{item.get('path', '')} "
                                f"{item.get('content', '')}"
                            )
                        ),
                        bool(
                            target_path
                            and str(item.get("path") or "").casefold()
                            == target_path.casefold()
                        ),
                    ),
                    reverse=True,
                )
                if not row.get("embedding_json")
            ][: self.settings.embedding_recall_batch_size]
            try:
                vectors = await self.embedding.embed(
                    [
                        query[:4_000],
                        *[
                            (
                                f"{row.get('path', '')}\n"
                                f"{row.get('content', '')}"
                            )[:4_000]
                            for row in pending
                        ],
                    ]
                )
                query_embedding = vectors[0] if vectors else None
                for row, vector in zip(pending, vectors[1:]):
                    row["embedding_json"] = json.dumps(vector)
                    await self.store.set_orientation_embedding(
                        row["id"],
                        vector,
                    )
            except Exception:
                query_embedding = None

        def row_score(row: dict[str, Any], *, strategy: bool) -> float:
            row_text = " ".join(
                str(row.get(key) or "")
                for key in (
                    "path",
                    "content",
                    "title",
                    "instruction",
                    "task_signature",
                )
            )
            row_tokens = _tokens(row_text)
            lexical = len(query_tokens & row_tokens) / max(1, len(query_tokens))
            path_bonus = (
                0.7
                if target_path
                and str(row.get("path") or "").casefold()
                == target_path.casefold()
                else 0.0
            )
            reliability = 0.0
            if strategy:
                helpful = int(row.get("helpful") or 0)
                harmful = int(row.get("harmful") or 0)
                reliability = (helpful + 1) / (helpful + harmful + 2)
            semantic = 0.0
            if query_embedding and row.get("embedding_json"):
                try:
                    semantic = _cosine(
                        query_embedding,
                        json.loads(row["embedding_json"]),
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    semantic = 0.0
            return lexical * 3.0 + semantic * 1.5 + path_bonus + reliability

        scored_strategies = sorted(
            (
                (row_score(row, strategy=True), row)
                for row in strategies
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        scored_orientations = sorted(
            (
                (row_score(row, strategy=False), row)
                for row in orientations
            ),
            key=lambda item: item[0],
            reverse=True,
        )

        lines = ["EXPERIENCE_KERNEL_V1 — verified, fixed-budget recall"]
        strategy_ids: list[str] = []
        orientation_ids: list[str] = []

        for candidate in active_candidates:
            try:
                payload = json.loads(candidate["payload_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            instruction = payload.get("instruction")
            if not isinstance(instruction, str) or not instruction.strip():
                continue
            line = (
                f"- ACTIVE_{candidate['kind'].upper()}: "
                f"{instruction.strip()}"
            )
            if len("\n".join([*lines, line])) > budget:
                break
            lines.append(line)

        for score, row in scored_strategies[:6]:
            if score <= 0.45:
                continue
            line = f"- PLAYBOOK: {row['instruction']}"
            if len("\n".join([*lines, line])) > budget:
                break
            lines.append(line)
            strategy_ids.append(row["id"])

        for score, row in scored_orientations[:10]:
            if score <= 0.15:
                continue
            line = (
                f"- ORIENTATION {row['path']} [{row['kind']}]: "
                f"{str(row['content']).replace(chr(10), ' | ')[:500]}"
            )
            if len("\n".join([*lines, line])) > budget:
                break
            lines.append(line)
            orientation_ids.append(row["id"])

        if len(lines) == 1:
            lines.append("- No sufficiently relevant verified experience yet.")
        text = "\n".join(lines)[:budget]
        await self.store.mark_recalled(orientation_ids)
        return RecallCapsule(
            text=text,
            task_signature=signature,
            strategy_ids=strategy_ids,
            orientation_ids=orientation_ids,
            chars=len(text),
            lexical_only=query_embedding is None,
        )

    @staticmethod
    def _language(paths: list[str]) -> str:
        suffixes = [Path(path).suffix.casefold() for path in paths]
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".html": "html",
            ".css": "css",
            ".json": "json",
        }
        return next((mapping[suffix] for suffix in suffixes if suffix in mapping), "mixed")

    async def record_verified_outcome(
        self,
        *,
        command_id: str,
        task_id: str,
        goal: str,
        title: str,
        verification: str,
        files: list[str],
        evidence: list[dict[str, Any]],
        success: bool,
        failure_kind: str | None = None,
        route_key: str | None = None,
        model: str | None = None,
        recalled_strategy_ids: list[str] | None = None,
        recalled_orientation_ids: list[str] | None = None,
    ) -> str:
        signature = self.task_signature(
            title=title,
            verification=verification,
            paths=files,
        )
        episode_id = await self.store.record_episode(
            {
                "project_key": self.project_key,
                "command_id": command_id,
                "task_id": task_id,
                "task_signature": signature,
                "goal": goal,
                "title": title,
                "language": self._language(files),
                "risk": "verified_write" if files else "read_only",
                "verification": verification,
                "success": success,
                "failure_kind": failure_kind,
                "route_key": route_key,
                "model": model,
                "files": files,
                "evidence": evidence,
                "recalled_strategy_ids": recalled_strategy_ids or [],
                "recalled_orientation_ids": recalled_orientation_ids or [],
            }
        )
        if success and episode_id:
            instruction = (
                f"For {self._language(files)} tasks with this shape, preserve the "
                f"exact file contract and verify with: {verification or 'the task-specific check'}."
            )
            await self.store.upsert_strategy(
                project_key=self.project_key,
                task_signature=signature,
                title=f"Verified playbook for {self._language(files)}",
                instruction=instruction,
                source_episode_id=episode_id,
            )
        return episode_id

    async def status(self) -> dict[str, Any]:
        status = await self.store.status(project_key=self.project_key)
        return {
            **status,
            "project_key": self.project_key,
            "router_mode": self.settings.learned_router_mode,
            "embedding_enabled": self.embedding is not None,
            "embedding_model": self.settings.ollama_embedding_model,
            "orientation_budget_chars": self.settings.orientation_cache_budget_chars,
            "source_mutation_enabled": self.settings.forge_source_mutation_enabled,
        }

    async def index_workspace(
        self,
        *,
        max_files: int = 120,
        build_embeddings: bool = True,
    ) -> dict[str, Any]:
        """Build a local outline index; never persists full source text."""

        root = self.workspace.root
        suffixes = {
            ".py",
            ".js",
            ".jsx",
            ".mjs",
            ".ts",
            ".tsx",
            ".html",
            ".css",
            ".json",
            ".md",
            ".toml",
            ".yaml",
            ".yml",
            ".sql",
        }
        indexed = 0
        skipped = 0
        if root.exists():
            for path in self.workspace.iter_files(root):
                if indexed >= max(1, min(max_files, 1_000)):
                    break
                relative = path.relative_to(root)
                if path.suffix.casefold() not in suffixes:
                    continue
                try:
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    skipped += 1
                    continue
                await self.remember_orientation(
                    path=relative.as_posix(),
                    source_sha256=hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest(),
                    outline=build_outline(relative.as_posix(), content),
                )
                indexed += 1

        embedded = 0
        if build_embeddings and self.embedding is not None:
            orientations, _strategies = await self.store.recall_rows(
                project_key=self.project_key,
                limit=max(1_000, max_files * 3),
            )
            pending = [
                row for row in orientations if not row.get("embedding_json")
            ]
            batch_size = self.settings.embedding_recall_batch_size
            for start in range(0, len(pending), batch_size):
                batch = pending[start:start + batch_size]
                try:
                    vectors = await self.embedding.embed(
                        [
                            (
                                f"{row.get('path', '')}\n"
                                f"{row.get('content', '')}"
                            )[:4_000]
                            for row in batch
                        ]
                    )
                except Exception:
                    break
                for row, vector in zip(batch, vectors):
                    await self.store.set_orientation_embedding(
                        row["id"],
                        vector,
                    )
                    embedded += 1
        return {
            "indexed_files": indexed,
            "embedded_entries": embedded,
            "skipped_files": skipped,
            "embedding_model": self.settings.ollama_embedding_model,
        }

    async def list_rows(self, table: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return await self.store.list_table(
            table,
            project_key=self.project_key,
            limit=limit,
        )
