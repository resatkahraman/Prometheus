from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from app.branding import (
    LEGACY_PROMOTION_CONFIRMATION,
    PROMOTION_CONFIRMATION,
)
from app.core.config import Settings
from app.improvement.benchmark import (
    ImprovementBenchmark,
    validate_candidate_payload,
)
from app.improvement.service import ImprovementService


class PrometheusForge:
    """Candidate -> isolated evaluation -> explicit promotion workflow."""

    def __init__(
        self,
        *,
        settings: Settings,
        improvement: ImprovementService,
    ) -> None:
        self.settings = settings
        self.improvement = improvement
        self.store = improvement.store
        self.benchmark = ImprovementBenchmark()

    async def create(
        self,
        *,
        kind: str,
        title: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.settings.forge_enabled:
            raise RuntimeError("Prometheus Forge is disabled.")
        return await self.store.create_candidate(
            project_key=self.improvement.project_key,
            kind=kind,
            title=title,
            payload=payload,
        )

    async def suggest_from_failures(self) -> list[dict[str, Any]]:
        episodes = await self.improvement.list_rows(
            "experience_episodes",
            limit=300,
        )
        failures: dict[str, int] = {}
        for episode in episodes:
            if int(episode.get("success") or 0):
                continue
            kind = str(episode.get("failure_kind") or "verification_failed")
            failures[kind] = failures.get(kind, 0) + 1
        if not failures:
            return [
                await self.create(
                    kind="prompt_delta",
                    title="Minimum exact edit discipline",
                    payload={
                        "instruction": (
                            "Prefer one hash-bound exact patch for existing "
                            "files; retain full-file output only for creation "
                            "or when a unique patch cannot be formed."
                        ),
                        "source": "bootstrap_safety_policy",
                    },
                )
            ]
        candidates: list[dict[str, Any]] = []
        for failure_kind, count in sorted(
            failures.items(),
            key=lambda item: (-item[1], item[0]),
        )[:5]:
            candidates.append(
                await self.create(
                    kind="strategy",
                    title=f"Repair playbook: {failure_kind}",
                    payload={
                        "instruction": (
                            f"When verification reports {failure_kind}, inspect "
                            "the exact evidence once, change strategy, and do "
                            "not repeat an identical command or file variant."
                        ),
                        "failure_kind": failure_kind,
                        "verified_failure_count": count,
                    },
                )
            )
        return candidates

    def _prepare_source_shadow(
        self,
        candidate: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.settings.forge_source_mutation_enabled:
            return {
                "prepared": False,
                "reason": "source_mutation_feature_lock_disabled",
            }
        root = Path(__file__).resolve().parents[2]
        relative = Path(str(payload["path"]).replace("\\", "/"))
        source = (root / relative).resolve()
        if root not in source.parents or not source.is_file():
            return {"prepared": False, "reason": "source_not_found_or_outside_root"}
        base = source.read_text(encoding="utf-8")
        sha256 = hashlib.sha256(base.encode("utf-8")).hexdigest()
        if sha256 != payload["base_sha256"]:
            return {"prepared": False, "reason": "stale_source_hash"}
        search = payload["search"]
        if base.count(search) != 1:
            return {"prepared": False, "reason": "search_not_unique"}
        updated = base.replace(search, payload["replacement"], 1)
        if source.suffix.casefold() == ".py":
            try:
                ast.parse(updated)
            except SyntaxError as exc:
                return {
                    "prepared": False,
                    "reason": "python_static_parse_failed",
                    "detail": str(exc),
                }
        lab_root = (
            self.settings.workspace_root.expanduser().resolve()
            / ".adam"
            / "forge"
            / "candidates"
            / candidate["id"]
        )
        shadow = (lab_root / relative).resolve()
        if lab_root not in shadow.parents:
            return {"prepared": False, "reason": "shadow_path_escape"}
        shadow.parent.mkdir(parents=True, exist_ok=True)
        shadow.write_text(updated, encoding="utf-8")
        manifest = {
            "candidate_id": candidate["id"],
            "source_path": relative.as_posix(),
            "base_sha256": sha256,
            "shadow_sha256": hashlib.sha256(
                updated.encode("utf-8")
            ).hexdigest(),
            "execution": "not_executed",
            "promotion": "manual_source_review_required",
        }
        (lab_root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"prepared": True, **manifest, "shadow_path": str(shadow)}

    async def evaluate(self, candidate_id: str) -> dict[str, Any]:
        candidate = await self.store.get_candidate(
            candidate_id,
            project_key=self.improvement.project_key,
        )
        payload = json.loads(candidate["payload_json"])
        validation_errors = validate_candidate_payload(
            candidate["kind"],
            payload,
        )
        shadow = None
        if candidate["kind"] == "source_patch" and not validation_errors:
            shadow = self._prepare_source_shadow(candidate, payload)
            if not shadow.get("prepared"):
                validation_errors.append(str(shadow.get("reason")))
        benchmark = self.benchmark.run(
            candidate_kind=candidate["kind"],
            candidate_payload=payload,
        )
        passed = (
            not validation_errors
            and benchmark["score"] >= 97.5
            and benchmark["passed"] == benchmark["total"]
        )
        evaluation = {
            **benchmark,
            "passed_gate": passed,
            "validation_errors": validation_errors,
            "source_shadow": shadow,
            "live_state_changed": False,
        }
        await self.store.record_benchmark(
            project_key=self.improvement.project_key,
            candidate_id=candidate_id,
            score=benchmark["score"],
            passed=benchmark["passed"],
            total=benchmark["total"],
            details=evaluation,
        )
        return await self.store.set_candidate_evaluation(
            candidate_id=candidate_id,
            project_key=self.improvement.project_key,
            evaluation=evaluation,
            passed=passed,
        )

    async def run_benchmark(
        self,
        candidate_id: str | None = None,
    ) -> dict[str, Any]:
        kind = None
        payload = None
        if candidate_id:
            candidate = await self.store.get_candidate(
                candidate_id,
                project_key=self.improvement.project_key,
            )
            kind = candidate["kind"]
            payload = json.loads(candidate["payload_json"])
        result = self.benchmark.run(
            candidate_kind=kind,
            candidate_payload=payload,
        )
        result["run_id"] = await self.store.record_benchmark(
            project_key=self.improvement.project_key,
            candidate_id=candidate_id,
            score=result["score"],
            passed=result["passed"],
            total=result["total"],
            details=result,
        )
        return result

    async def promote(
        self,
        candidate_id: str,
        *,
        confirmation: str,
    ) -> dict[str, Any]:
        if confirmation.strip() not in {
            PROMOTION_CONFIRMATION,
            LEGACY_PROMOTION_CONFIRMATION,
        }:
            raise ValueError("Promotion requires the exact explicit confirmation.")
        candidate = await self.store.get_candidate(
            candidate_id,
            project_key=self.improvement.project_key,
        )
        if candidate["kind"] == "source_patch":
            raise ValueError(
                "Source patches are lab-only and cannot be promoted automatically."
            )
        return await self.store.promote_candidate(
            candidate_id=candidate_id,
            project_key=self.improvement.project_key,
        )

    async def rollback(self, candidate_id: str) -> dict[str, Any]:
        return await self.store.rollback_candidate(
            candidate_id=candidate_id,
            project_key=self.improvement.project_key,
        )


# Backward-compatible import for extensions written before the rebrand.
AdamForge = PrometheusForge
