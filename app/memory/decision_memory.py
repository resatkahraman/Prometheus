from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import threading
import unicodedata
from typing import Any

from app.core.schemas import (
    DecisionMemoryCreateRequest,
    DecisionMemoryPage,
    DecisionMemoryRecord,
    DecisionMemoryScope,
    DecisionMemorySourceRef,
    DecisionMemoryWriteResponse,
    DecisionMemoryScopeKind,
)
from app.tools.base import ToolError
from app.workspace.policy import WorkspacePolicy

DECISION_MEMORY_SCHEMA_VERSION = 1
DECISION_MEMORY_STATE_DIRECTORY = ".adam"
DECISION_MEMORY_FILENAME = "decision_memory.json"
DECISION_MEMORY_IDEMPOTENCY_LIMIT = 128

_ID_RE = re.compile(r"^dmem_[0-9a-f]{32}$")
_PROJECT_ID_RE = re.compile(r"^dmemproj_[0-9a-f]{32}$")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_RE = re.compile(r"(?i)(?<![a-z0-9_])(?:authorization|cookie|set-cookie|token|access_token|refresh_token|session_token|http_auth_token|pandora_token|api_key|apikey|password|passwd|secret|credential|credentials|private_key)\b\s*[=:]\s*\S+")
_HOST_PATH_RE = re.compile(r"(?i)(?:^|[\s\"'=:\\])(?:[a-z]:[\\/]|\\\\[^\\s]+[\\/]|/(?:home|users|root|tmp)/)")
_COMMAND_RE = re.compile(r"(?:\r|\n|&&|\|\||[;|<>]|`|\$\()")


class DecisionMemoryError(RuntimeError):
    pass


class DecisionMemoryValidationError(DecisionMemoryError):
    pass


class DecisionMemoryConflictError(DecisionMemoryError):
    pass


class DecisionMemoryIntegrityError(DecisionMemoryError):
    pass


class DecisionMemoryNotFoundError(DecisionMemoryError):
    pass


@dataclass(frozen=True)
class DecisionMemoryContext:
    workspace_path: str
    project_id: str
    store_revision: int
    store_digest: str
    decision_ids: tuple[str, ...]
    text: str
    chars: int

    def to_prompt_payload(self) -> dict[str, object]:
        return {
            "state": "present",
            "workspace_path": self.workspace_path,
            "project_id": self.project_id,
            "store_revision": self.store_revision,
            "store_digest": self.store_digest,
            "decision_ids": list(self.decision_ids),
            "context": self.text,
            "context_chars": self.chars,
        }


def normalize_decision_text(value: str, *, field_name: str, max_chars: int) -> str:
    if not isinstance(value, str):
        raise DecisionMemoryValidationError(f"{field_name} must be text.")
    value = unicodedata.normalize("NFC", value).strip()
    if not value or len(value) > max_chars:
        raise DecisionMemoryValidationError(f"{field_name} is invalid.")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise DecisionMemoryValidationError(f"{field_name} is invalid.")
    lowered = value.casefold()
    if (_SECRET_RE.search(value) or "-----begin" in lowered or "traceback (most recent call last)" in lowered or _HOST_PATH_RE.search(value)):
        raise DecisionMemoryValidationError(f"{field_name} contains unsafe text.")
    return value


def decision_text_digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


class DecisionMemoryManager:
    def __init__(self, *, workspace_root: Path, enabled: bool = True, max_file_bytes: int = 1_048_576, max_records: int = 512, max_context_chars: int = 12_000, max_results: int = 100, max_search_results: int = 1_000) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.enabled = bool(enabled)
        self.max_file_bytes = max_file_bytes
        self.max_records = max_records
        self.max_context_chars = max_context_chars
        self.max_results = max_results
        self.workspace = WorkspacePolicy(root=self.workspace_root, max_file_bytes=max_file_bytes, max_search_results=max_search_results)
        self._lock = threading.RLock()

    def _resolve_project_root(self, workspace_path: str) -> tuple[str, Path]:
        try:
            root = self.workspace.resolve(workspace_path, must_exist=True)
        except ToolError as exc:
            raise DecisionMemoryValidationError("Project workspace is invalid.") from exc
        if not root.is_dir() or root.is_symlink():
            raise DecisionMemoryValidationError("Project workspace is invalid.")
        return self.workspace.relative(root), root

    def _state_path(self, project_root: Path) -> Path:
        state_dir = project_root / DECISION_MEMORY_STATE_DIRECTORY
        if state_dir.exists() and (state_dir.is_symlink() or not state_dir.is_dir()):
            raise DecisionMemoryIntegrityError("Decision Memory state directory is invalid.")
        return state_dir / DECISION_MEMORY_FILENAME

    @staticmethod
    def _canonical_json_bytes(value: object) -> bytes:
        return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")

    @classmethod
    def _canonical_digest(cls, value: object) -> str:
        return "sha256:" + hashlib.sha256(cls._canonical_json_bytes(value)).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _normalize_scope(self, scope: DecisionMemoryScope) -> DecisionMemoryScope:
        ref = scope.ref.strip() if scope.ref else None
        if scope.kind == "project":
            return DecisionMemoryScope(kind="project", ref=None)
        if not ref:
            raise DecisionMemoryValidationError("Decision scope ref is required.")
        if scope.kind == "path":
            ref = self._normalize_path(ref)
        return DecisionMemoryScope(kind=scope.kind, ref=ref)

    def _normalize_path(self, value: str) -> str:
        value = normalize_decision_text(value, field_name="path", max_chars=500).replace("\\", "/")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or ":" in value or not path.parts:
            raise DecisionMemoryValidationError("Decision path is invalid.")
        return PurePosixPath(*[part for part in path.parts if part not in {"", "."}]).as_posix()

    def _normalize_sources(self, refs: list[DecisionMemorySourceRef], project_root: Path) -> list[DecisionMemorySourceRef]:
        result: list[DecisionMemorySourceRef] = []
        for source in refs:
            value = normalize_decision_text(source.value, field_name="source", max_chars=1_000)
            if source.kind == "user" and value != "explicit":
                raise DecisionMemoryValidationError("User provenance is invalid.")
            if source.kind == "commit" and re.fullmatch(r"[0-9a-f]{40}", value) is None:
                raise DecisionMemoryValidationError("Commit provenance is invalid.")
            if source.kind == "file":
                value = self._normalize_path(value)
                if not (project_root / value).is_file():
                    raise DecisionMemoryValidationError("File provenance is invalid.")
            if source.digest is not None and not _HASH_RE.fullmatch(source.digest):
                raise DecisionMemoryValidationError("Source digest is invalid.")
            result.append(DecisionMemorySourceRef(kind=source.kind, value=value, digest=source.digest))
        return result

    def _record_payload(self, record: DecisionMemoryRecord) -> dict[str, Any]:
        data = record.model_dump(mode="json")
        data.pop("status", None)
        data.pop("record_hash", None)
        return data

    def _record_hash(self, record: DecisionMemoryRecord) -> str:
        return self._canonical_digest(self._record_payload(record))

    def _store_digest(self, document: dict[str, Any]) -> str:
        payload = dict(document)
        payload.pop("store_digest", None)
        return self._canonical_digest(payload)

    def _load(self, workspace_path: str) -> tuple[str, Path, dict[str, Any] | None]:
        normalized, root = self._resolve_project_root(workspace_path)
        if not self.enabled:
            return normalized, root, None
        path = self._state_path(root)
        if not path.exists():
            return normalized, root, None
        if path.is_symlink() or not path.is_file():
            raise DecisionMemoryIntegrityError("Decision Memory state file is invalid.")
        if path.stat().st_size > self.max_file_bytes:
            raise DecisionMemoryIntegrityError("Decision Memory state file exceeds its size limit.")
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise DecisionMemoryIntegrityError("Decision Memory state is invalid.") from exc
        required = {"schema_version", "project_id", "store_revision", "updated_at", "idempotency_receipts", "records", "store_digest"}
        if not isinstance(document, dict) or set(document) != required or document.get("schema_version") != 1:
            raise DecisionMemoryIntegrityError("Decision Memory state is invalid.")
        if not isinstance(document["project_id"], str) or not _PROJECT_ID_RE.fullmatch(document["project_id"]):
            raise DecisionMemoryIntegrityError("Decision Memory identity is invalid.")
        if not isinstance(document["store_revision"], int) or document["store_revision"] < 1:
            raise DecisionMemoryIntegrityError("Decision Memory revision is invalid.")
        if document.get("store_digest") != self._store_digest(document):
            raise DecisionMemoryIntegrityError("Decision Memory store integrity conflict.")
        if len(document["records"]) > self.max_records or len(document["idempotency_receipts"]) > DECISION_MEMORY_IDEMPOTENCY_LIMIT:
            raise DecisionMemoryIntegrityError("Decision Memory bounds exceeded.")
        for raw in document["records"]:
            if not isinstance(raw, dict) or "status" in raw:
                raise DecisionMemoryIntegrityError("Decision Memory record is invalid.")
            try:
                record = DecisionMemoryRecord.model_validate({**raw, "status": "active"})
            except Exception as exc:
                raise DecisionMemoryIntegrityError("Decision Memory record is invalid.") from exc
            if record.record_hash != self._record_hash(record):
                raise DecisionMemoryIntegrityError("Decision Memory record integrity conflict.")
        return normalized, root, document

    @staticmethod
    def _status_map(records: list[dict[str, Any]]) -> dict[str, str]:
        superseded = {r["supersedes"] for r in records if r.get("supersedes")}
        return {r["decision_id"]: ("superseded" if r["decision_id"] in superseded else "active") for r in records}

    def _records(self, document: dict[str, Any]) -> list[DecisionMemoryRecord]:
        statuses = self._status_map(document["records"])
        return [DecisionMemoryRecord.model_validate({**raw, "status": statuses[raw["decision_id"]]}) for raw in document["records"]]

    def _response(self, workspace_path: str, document: dict[str, Any], record: DecisionMemoryRecord, *, created: bool, replayed: bool) -> DecisionMemoryWriteResponse:
        return DecisionMemoryWriteResponse(workspace_path=workspace_path, project_id=document["project_id"], store_revision=document["store_revision"], store_digest=document["store_digest"], record=record, created=created, replayed=replayed, side_effect_free=False)

    def list(self, *, workspace_path: str = ".", active_only: bool = True, scope_kind: DecisionMemoryScopeKind | None = None, after_revision: int | None = None, limit: int = 50) -> DecisionMemoryPage:
        with self._lock:
            normalized, _root, document = self._load(workspace_path)
            if document is None:
                return DecisionMemoryPage(workspace_path=normalized, state="missing", side_effect_free=True)
            items = self._records(document)
            if active_only: items = [item for item in items if item.status == "active"]
            if scope_kind: items = [item for item in items if item.scope.kind == scope_kind]
            if after_revision is not None: items = [item for item in items if item.store_revision > after_revision]
            items = items[: max(1, min(limit, self.max_results))]
            return DecisionMemoryPage(workspace_path=normalized, state="present", project_id=document["project_id"], store_revision=document["store_revision"], store_digest=document["store_digest"], items=items, total=len(items), next_after_revision=items[-1].store_revision if items else None)

    def read(self, *, workspace_path: str, decision_id: str) -> DecisionMemoryRecord:
        page = self.list(workspace_path=workspace_path, active_only=False, limit=self.max_records)
        for record in page.items:
            if record.decision_id == decision_id: return record
        raise DecisionMemoryNotFoundError("Decision Memory record not found.")

    def create(self, request: DecisionMemoryCreateRequest) -> DecisionMemoryWriteResponse:
        if request.confirmation != "record_decision": raise DecisionMemoryValidationError("Explicit confirmation is required.")
        with self._lock:
            normalized, root, document = self._load(request.workspace_path)
            content = {"title": normalize_decision_text(request.title, field_name="title", max_chars=160), "context": normalize_decision_text(request.context, field_name="context", max_chars=4_000), "decision": normalize_decision_text(request.decision, field_name="decision", max_chars=4_000), "reason": normalize_decision_text(request.reason, field_name="reason", max_chars=4_000)}
            scope = self._normalize_scope(request.scope)
            sources = self._normalize_sources(request.source_refs, root)
            key_hash = decision_text_digest(request.idempotency_key.strip())
            fingerprint = self._canonical_digest({"key": key_hash, "decision_key": request.decision_key, **content, "scope": scope.model_dump(mode="json"), "sources": [s.model_dump(mode="json") for s in sources], "supersedes": request.supersedes})
            if document is not None:
                for receipt in document["idempotency_receipts"]:
                    if hmac.compare_digest(receipt["key_hash"], key_hash):
                        if receipt["request_fingerprint"] != fingerprint: raise DecisionMemoryConflictError("Decision Memory idempotency conflict.")
                        record = self.read(workspace_path=normalized, decision_id=receipt["decision_id"])
                        return self._response(normalized, document, record, created=False, replayed=True)
            if document is None:
                document = {"schema_version": 1, "project_id": "dmemproj_" + secrets.token_hex(16), "store_revision": 0, "updated_at": self._now(), "idempotency_receipts": [], "records": [], "store_digest": ""}
            if request.expected_store_revision != document["store_revision"] or (document["store_revision"] and request.expected_store_digest != document["store_digest"]):
                raise DecisionMemoryConflictError("Decision Memory store conflict.")
            records = self._records(document) if document["records"] else []
            active = [r for r in records if r.status == "active" and r.decision_key == request.decision_key and r.scope == scope]
            if active and request.supersedes is None: raise DecisionMemoryConflictError("Active decision requires explicit supersedes.")
            if request.supersedes is not None:
                old = next((r for r in records if r.decision_id == request.supersedes), None)
                if old is None or old.status != "active" or old.decision_key != request.decision_key or old.scope != scope: raise DecisionMemoryConflictError("Supersedes target is invalid.")
                revision = old.decision_revision + 1
            else: revision = max((r.decision_revision for r in records if r.decision_key == request.decision_key), default=0) + 1
            store_revision = document["store_revision"] + 1
            record = DecisionMemoryRecord(schema_version=1, decision_id="dmem_" + secrets.token_hex(16), decision_key=request.decision_key, decision_revision=revision, store_revision=store_revision, title=content["title"], context=content["context"], decision=content["decision"], reason=content["reason"], alternatives=[normalize_decision_text(v, field_name="alternative", max_chars=1_000) for v in request.alternatives], consequences=[normalize_decision_text(v, field_name="consequence", max_chars=1_000) for v in request.consequences], scope=scope, source_refs=sources, created_in_mission=request.created_in_mission, supersedes=request.supersedes, status="active", created_at=self._now(), record_hash="sha256:" + "0" * 64)
            record.record_hash = self._record_hash(record)
            document["records"].append({k: v for k, v in record.model_dump(mode="json").items() if k not in {"status", "record_hash"}} | {"record_hash": record.record_hash})
            document["store_revision"] = store_revision; document["updated_at"] = self._now(); document["idempotency_receipts"].append({"key_hash": key_hash, "request_fingerprint": fingerprint, "decision_id": record.decision_id, "store_revision": store_revision}); document["idempotency_receipts"] = document["idempotency_receipts"][-DECISION_MEMORY_IDEMPOTENCY_LIMIT:]; document["store_digest"] = self._store_digest(document)
            self._atomic_write(project_root=root, document=document)
            return self._response(normalized, document, record, created=True, replayed=False)

    def context(self, *, workspace_path: str = ".", mission_id: str | None = None, branch_name: str | None = None, paths: list[str] | None = None) -> DecisionMemoryContext | None:
        page = self.list(workspace_path=workspace_path, active_only=True, limit=self.max_results)
        if page.state == "missing" or not page.items: return None
        selected = [r for r in page.items if r.scope.kind == "project" or (r.scope.kind == "mission" and r.scope.ref == mission_id) or (r.scope.kind == "branch" and r.scope.ref == branch_name) or (r.scope.kind == "path" and paths and r.scope.ref in paths)]
        if not selected: return None
        lines = ["DECISION_MEMORY_V1", f"store_digest={page.store_digest}"]
        for record in selected:
            lines.extend([f"[{record.decision_key}] {record.title}", f"decision: {record.decision}", f"reason: {record.reason}"])
        text = "\n".join(lines); text = text[: self.max_context_chars]
        return DecisionMemoryContext(workspace_path=page.workspace_path, project_id=page.project_id or "", store_revision=page.store_revision, store_digest=page.store_digest or "", decision_ids=tuple(r.decision_id for r in selected), text=text, chars=len(text))

    def find_active(self, *, workspace_path: str = ".", decision_key: str, mission_id: str | None = None, branch_name: str | None = None, paths: list[str] | None = None) -> DecisionMemoryRecord | None:
        page = self.list(workspace_path=workspace_path, active_only=True, limit=self.max_results)
        for record in page.items:
            if record.decision_key == decision_key and (record.scope.kind == "project" or (record.scope.kind == "mission" and record.scope.ref == mission_id) or (record.scope.kind == "branch" and record.scope.ref == branch_name) or (record.scope.kind == "path" and paths and record.scope.ref in paths)): return record
        return None

    def _atomic_write(self, *, project_root: Path, document: dict[str, Any]) -> None:
        state_dir = project_root / DECISION_MEMORY_STATE_DIRECTORY; state_dir.mkdir(parents=True, exist_ok=True); path = state_dir / DECISION_MEMORY_FILENAME
        payload = self._canonical_json_bytes(document)
        if len(payload) > self.max_file_bytes: raise DecisionMemoryValidationError("Decision Memory state exceeds its size limit.")
        temporary = state_dir / f".{DECISION_MEMORY_FILENAME}.{secrets.token_hex(8)}.tmp"
        try:
            with temporary.open("xb") as stream: stream.write(payload); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc: raise DecisionMemoryError("Decision Memory state could not be written.") from exc
        finally:
            if temporary.exists():
                try: temporary.unlink()
                except OSError: pass
