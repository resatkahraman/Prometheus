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
from typing import Any

from pydantic import ValidationError

from app.core.schemas import (
    ProjectDNAContent,
    ProjectDNAResponse,
    ProjectDNAUpdateRequest,
)
from app.tools.base import ToolError
from app.workspace.policy import WorkspacePolicy


PROJECT_DNA_FILENAME = "PROJECT_DNA.json"
PROJECT_DNA_SCHEMA_VERSION = 1

_PROJECT_ID_RE = re.compile(r"^pdna_[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_SECRET_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    (?<![a-z0-9_])
    (?:
        authorization
        | cookie
        | set-cookie
        | token
        | access_token
        | refresh_token
        | session_token
        | http_auth_token
        | pandora_token
        | api_key
        | apikey
        | password
        | passwd
        | secret
        | credential
        | credentials
        | private_key
    )
    (?![a-z0-9_])
    \s*[=:]\s*\S+
    """
)

_HOST_PATH_RE = re.compile(
    r"""(?ix)
    (?:
        ^ |
        [\s"'=:]
    )
    (?:
        [a-z]:[\\/]
        | \\\\[^\\\s]+[\\/]
        | /(?:home|users|root|tmp)/
    )
    """
)

_COMMAND_OPERATOR_RE = re.compile(
    r"(?:\r|\n|&&|\|\||[;|<>]|`|\$\()"
)

_PEM_MARKERS = (
    "-----begin private key-----",
    "-----begin rsa private key-----",
    "-----begin ec private key-----",
    "-----begin openssh private key-----",
)

_TRACEBACK_MARKER = "traceback (most recent call last)"

_DOCUMENT_KEYS = frozenset(
    {
        "schema_version",
        "project_id",
        "revision",
        "updated_at",
        "last_idempotency_key_hash",
        "last_update_fingerprint",
        "content",
    }
)


class ProjectDNAError(RuntimeError):
    """Base error for Project DNA operations."""


class ProjectDNAValidationError(ProjectDNAError):
    """Raised when a request or document violates the Project DNA contract."""


class ProjectDNAConflictError(ProjectDNAError):
    """Raised for optimistic-concurrency or idempotency conflicts."""


class ProjectDNAIntegrityError(ProjectDNAError):
    """Raised when an existing Project DNA source fails closed."""


@dataclass(frozen=True)
class ProjectDNAContext:
    workspace_path: str
    source_file: str
    project_id: str
    revision: int
    digest: str
    text: str
    chars: int

    def to_prompt_payload(self) -> dict[str, object]:
        return {
            "state": "present",
            "workspace_path": self.workspace_path,
            "source_file": self.source_file,
            "project_id": self.project_id,
            "revision": self.revision,
            "digest": self.digest,
            "context": self.text,
            "context_chars": self.chars,
        }


@dataclass(frozen=True)
class _ProjectDNARecord:
    workspace_path: str
    project_root: Path
    project_id: str
    revision: int
    digest: str
    updated_at: str
    last_idempotency_key_hash: str
    last_update_fingerprint: str
    content: ProjectDNAContent


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _canonical_digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest()


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _validate_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProjectDNAIntegrityError(
            "Project DNA timestamp is invalid."
        )

    normalized = value.strip()

    try:
        parsed = datetime.fromisoformat(
            normalized.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ProjectDNAIntegrityError(
            "Project DNA timestamp is invalid."
        ) from exc

    if parsed.tzinfo is None:
        raise ProjectDNAIntegrityError(
            "Project DNA timestamp is invalid."
        )

    return normalized


def _contains_control_character(value: str) -> bool:
    return any(
        ord(character) < 32
        and character not in {"\n", "\t"}
        for character in value
    )


def _contains_unsafe_text(value: str) -> bool:
    lowered = value.casefold()

    return (
        "\x00" in value
        or _contains_control_character(value)
        or _SECRET_ASSIGNMENT_RE.search(value) is not None
        or _HOST_PATH_RE.search(value) is not None
        or _TRACEBACK_MARKER in lowered
        or any(marker in lowered for marker in _PEM_MARKERS)
    )


def _normalize_text(
    value: object,
    *,
    field: str,
    max_chars: int,
    allow_newlines: bool,
) -> str:
    if not isinstance(value, str):
        raise ProjectDNAValidationError(
            f"{field} must be text."
        )

    normalized = (
        value.replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )

    if not normalized:
        raise ProjectDNAValidationError(
            f"{field} may not be empty."
        )

    if len(normalized) > max_chars:
        raise ProjectDNAValidationError(
            f"{field} exceeds its size limit."
        )

    if not allow_newlines and "\n" in normalized:
        raise ProjectDNAValidationError(
            f"{field} must be one line."
        )

    if _contains_unsafe_text(normalized):
        raise ProjectDNAValidationError(
            f"{field} contains unsafe state."
        )

    return normalized


def _stable_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


def _normalize_text_list(
    values: object,
    *,
    field: str,
    maximum_items: int,
    item_max_chars: int = 1_000,
) -> list[str]:
    if not isinstance(values, list):
        raise ProjectDNAValidationError(
            f"{field} must be a list."
        )

    if len(values) > maximum_items:
        raise ProjectDNAValidationError(
            f"{field} contains too many items."
        )

    normalized = [
        _normalize_text(
            item,
            field=field,
            max_chars=item_max_chars,
            allow_newlines=False,
        )
        for item in values
    ]

    return _stable_unique(normalized)


def _normalize_relative_path(
    value: object,
    *,
    field: str,
    project_policy: WorkspacePolicy,
) -> str:
    normalized = _normalize_text(
        value,
        field=field,
        max_chars=500,
        allow_newlines=False,
    ).replace("\\", "/")

    path = PurePosixPath(normalized)

    if (
        path.is_absolute()
        or ".." in path.parts
        or ":" in normalized
    ):
        raise ProjectDNAValidationError(
            f"{field} contains an unsafe path."
        )

    parts = [
        part
        for part in path.parts
        if part not in {"", "."}
    ]

    if not parts:
        raise ProjectDNAValidationError(
            f"{field} contains an empty path."
        )

    result = PurePosixPath(*parts).as_posix()

    try:
        project_policy.ensure_not_sensitive(result)
    except ToolError as exc:
        raise ProjectDNAValidationError(
            f"{field} contains an unsafe path."
        ) from exc

    return result


def _normalize_path_list(
    values: object,
    *,
    field: str,
    maximum_items: int,
    project_policy: WorkspacePolicy,
) -> list[str]:
    if not isinstance(values, list):
        raise ProjectDNAValidationError(
            f"{field} must be a list."
        )

    if len(values) > maximum_items:
        raise ProjectDNAValidationError(
            f"{field} contains too many items."
        )

    normalized = [
        _normalize_relative_path(
            item,
            field=field,
            project_policy=project_policy,
        )
        for item in values
    ]

    return _stable_unique(normalized)


def _normalize_command_list(
    values: object,
    *,
    field: str,
) -> list[str]:
    commands = _normalize_text_list(
        values,
        field=field,
        maximum_items=32,
        item_max_chars=500,
    )

    for command in commands:
        if _COMMAND_OPERATOR_RE.search(command):
            raise ProjectDNAValidationError(
                f"{field} contains a compound or unsafe command."
            )

    return commands


def _normalize_content(
    content: ProjectDNAContent,
    *,
    project_root: Path,
    max_file_bytes: int,
    max_search_results: int,
) -> ProjectDNAContent:
    project_policy = WorkspacePolicy(
        root=project_root,
        max_file_bytes=max_file_bytes,
        max_search_results=max_search_results,
    )

    return ProjectDNAContent(
        name=_normalize_text(
            content.name,
            field="name",
            max_chars=160,
            allow_newlines=False,
        ),
        purpose=_normalize_text(
            content.purpose,
            field="purpose",
            max_chars=4_000,
            allow_newlines=True,
        ),
        technologies=_normalize_text_list(
            content.technologies,
            field="technologies",
            maximum_items=64,
        ),
        architecture=_normalize_text_list(
            content.architecture,
            field="architecture",
            maximum_items=64,
        ),
        invariants=_normalize_text_list(
            content.invariants,
            field="invariants",
            maximum_items=128,
        ),
        conventions=_normalize_text_list(
            content.conventions,
            field="conventions",
            maximum_items=128,
        ),
        key_paths=_normalize_path_list(
            content.key_paths,
            field="key_paths",
            maximum_items=128,
            project_policy=project_policy,
        ),
        build_commands=_normalize_command_list(
            content.build_commands,
            field="build_commands",
        ),
        test_commands=_normalize_command_list(
            content.test_commands,
            field="test_commands",
        ),
        verification_rules=_normalize_text_list(
            content.verification_rules,
            field="verification_rules",
            maximum_items=128,
        ),
        protected_paths=_normalize_path_list(
            content.protected_paths,
            field="protected_paths",
            maximum_items=128,
            project_policy=project_policy,
        ),
    )


class ProjectDNAManager:
    def __init__(
        self,
        *,
        workspace_root: Path,
        enabled: bool = True,
        max_file_bytes: int = 32_768,
        max_context_chars: int = 8_000,
        max_search_results: int = 1_000,
    ) -> None:
        self.workspace_root = (
            workspace_root.expanduser().resolve()
        )
        self.enabled = bool(enabled)
        self.max_file_bytes = max_file_bytes
        self.max_context_chars = max_context_chars
        self.max_search_results = max_search_results
        self.workspace = WorkspacePolicy(
            root=self.workspace_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )
        self._lock = threading.RLock()

    def _resolve_project_root(
        self,
        workspace_path: str,
    ) -> tuple[str, Path]:
        try:
            project_root = self.workspace.resolve(
                workspace_path,
                must_exist=True,
            )
        except ToolError as exc:
            raise ProjectDNAValidationError(
                "Project workspace is invalid."
            ) from exc

        if not project_root.is_dir():
            raise ProjectDNAValidationError(
                "Project workspace is invalid."
            )

        if project_root.is_symlink():
            raise ProjectDNAValidationError(
                "Project workspace is invalid."
            )

        normalized = self.workspace.relative(
            project_root
        )

        return normalized, project_root

    @staticmethod
    def _dna_path(project_root: Path) -> Path:
        candidate = (
            project_root / PROJECT_DNA_FILENAME
        ).resolve(strict=False)

        if candidate.parent != project_root.resolve():
            raise ProjectDNAValidationError(
                "Project DNA source path is invalid."
            )

        return candidate

    def _record_from_document(
        self,
        *,
        workspace_path: str,
        project_root: Path,
        document: object,
    ) -> _ProjectDNARecord:
        if not isinstance(document, dict):
            raise ProjectDNAIntegrityError(
                "Project DNA document is invalid."
            )

        if set(document) != _DOCUMENT_KEYS:
            raise ProjectDNAIntegrityError(
                "Project DNA document is invalid."
            )

        if (
            document.get("schema_version")
            != PROJECT_DNA_SCHEMA_VERSION
        ):
            raise ProjectDNAIntegrityError(
                "Project DNA schema version is unsupported."
            )

        project_id = document.get("project_id")
        revision = document.get("revision")
        updated_at = _validate_timestamp(
            document.get("updated_at")
        )
        idempotency_hash = document.get(
            "last_idempotency_key_hash"
        )
        update_fingerprint = document.get(
            "last_update_fingerprint"
        )

        if (
            not isinstance(project_id, str)
            or _PROJECT_ID_RE.fullmatch(project_id) is None
        ):
            raise ProjectDNAIntegrityError(
                "Project DNA project identity is invalid."
            )

        if (
            not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
        ):
            raise ProjectDNAIntegrityError(
                "Project DNA revision is invalid."
            )

        if (
            not isinstance(idempotency_hash, str)
            or _SHA256_RE.fullmatch(idempotency_hash)
            is None
        ):
            raise ProjectDNAIntegrityError(
                "Project DNA idempotency state is invalid."
            )

        if (
            not isinstance(update_fingerprint, str)
            or _SHA256_RE.fullmatch(update_fingerprint)
            is None
        ):
            raise ProjectDNAIntegrityError(
                "Project DNA update state is invalid."
            )

        try:
            parsed_content = (
                ProjectDNAContent.model_validate(
                    document.get("content")
                )
            )
        except ValidationError as exc:
            raise ProjectDNAIntegrityError(
                "Project DNA content is invalid."
            ) from exc

        try:
            content = _normalize_content(
                parsed_content,
                project_root=project_root,
                max_file_bytes=self.max_file_bytes,
                max_search_results=(
                    self.max_search_results
                ),
            )
        except ProjectDNAValidationError as exc:
            raise ProjectDNAIntegrityError(
                "Project DNA content is invalid."
            ) from exc

        canonical_document = {
            "schema_version": (
                PROJECT_DNA_SCHEMA_VERSION
            ),
            "project_id": project_id,
            "revision": revision,
            "updated_at": updated_at,
            "last_idempotency_key_hash": (
                idempotency_hash
            ),
            "last_update_fingerprint": (
                update_fingerprint
            ),
            "content": content.model_dump(
                mode="json"
            ),
        }

        return _ProjectDNARecord(
            workspace_path=workspace_path,
            project_root=project_root,
            project_id=project_id,
            revision=revision,
            digest=_canonical_digest(
                       {
                           "schema_version": PROJECT_DNA_SCHEMA_VERSION,
                           "revision": revision,
                           "content": content.model_dump(
                               mode="json"
                           ),
                       }
                   ),
            updated_at=updated_at,
            last_idempotency_key_hash=(
                idempotency_hash
            ),
            last_update_fingerprint=(
                update_fingerprint
            ),
            content=content,
        )

    def _read_record(
        self,
        workspace_path: str,
    ) -> tuple[
        str,
        Path,
        _ProjectDNARecord | None,
    ]:
        normalized, project_root = (
            self._resolve_project_root(
                workspace_path
            )
        )

        if not self.enabled:
            return normalized, project_root, None

        path = self._dna_path(project_root)

        if not path.exists():
            return normalized, project_root, None

        if (
            path.is_symlink()
            or not path.is_file()
        ):
            raise ProjectDNAIntegrityError(
                "Project DNA source is invalid."
            )

        try:
            size = path.stat().st_size
        except OSError as exc:
            raise ProjectDNAIntegrityError(
                "Project DNA source cannot be read."
            ) from exc

        if size > self.max_file_bytes:
            raise ProjectDNAIntegrityError(
                "Project DNA source exceeds its size limit."
            )

        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError) as exc:
            raise ProjectDNAIntegrityError(
                "Project DNA source cannot be read."
            ) from exc

        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProjectDNAIntegrityError(
                "Project DNA source is not valid JSON."
            ) from exc

        record = self._record_from_document(
            workspace_path=normalized,
            project_root=project_root,
            document=document,
        )

        return normalized, project_root, record

    def _render_context(
        self,
        record: _ProjectDNARecord,
    ) -> str:
        content = record.content

        blocks: list[str] = [
            "PROJECT_DNA_V1",
            f"source={PROJECT_DNA_FILENAME}",
            f"project_id={record.project_id}",
            f"revision={record.revision}",
            f"digest={record.digest}",
            "",
            "[NAME]",
            content.name,
            "",
            "[PURPOSE]",
            content.purpose,
        ]

        sections: tuple[
            tuple[str, list[str]],
            ...,
        ] = (
            ("TECHNOLOGIES", content.technologies),
            ("ARCHITECTURE", content.architecture),
            ("INVARIANTS", content.invariants),
            ("CONVENTIONS", content.conventions),
            ("KEY_PATHS", content.key_paths),
            ("BUILD_COMMANDS", content.build_commands),
            ("TEST_COMMANDS", content.test_commands),
            (
                "VERIFICATION_RULES",
                content.verification_rules,
            ),
            (
                "PROTECTED_PATHS",
                content.protected_paths,
            ),
        )

        for title, values in sections:
            if not values:
                continue

            blocks.extend(
                [
                    "",
                    f"[{title}]",
                    *(
                        f"- {value}"
                        for value in values
                    ),
                ]
            )

        rendered = "\n".join(blocks).strip()

        if len(rendered) <= self.max_context_chars:
            return rendered

        marker = (
            "\n[TRUNCATED_BY_PROJECT_DNA_BUDGET]"
        )

        available = max(
            1,
            self.max_context_chars - len(marker),
        )

        return rendered[:available] + marker

    def _response(
        self,
        *,
        workspace_path: str,
        record: _ProjectDNARecord | None,
        created: bool = False,
        updated: bool = False,
        replayed: bool = False,
        side_effect_free: bool,
    ) -> ProjectDNAResponse:
        if record is None:
            return ProjectDNAResponse(
                workspace_path=workspace_path,
                state="missing",
                revision=0,
                context_chars=0,
                created=False,
                updated=False,
                replayed=False,
                side_effect_free=side_effect_free,
            )

        context = self._render_context(record)

        return ProjectDNAResponse(
            workspace_path=workspace_path,
            state="present",
            project_id=record.project_id,
            revision=record.revision,
            digest=record.digest,
            updated_at=record.updated_at,
            content=record.content.model_copy(
                deep=True
            ),
            context_chars=len(context),
            created=created,
            updated=updated,
            replayed=replayed,
            side_effect_free=side_effect_free,
        )

    def read(
        self,
        workspace_path: str = ".",
    ) -> ProjectDNAResponse:
        with self._lock:
            normalized, _root, record = (
                self._read_record(workspace_path)
            )

            return self._response(
                workspace_path=normalized,
                record=record,
                side_effect_free=True,
            )

    def context(
        self,
        workspace_path: str = ".",
    ) -> ProjectDNAContext | None:
        with self._lock:
            normalized, _root, record = (
                self._read_record(workspace_path)
            )

            if record is None:
                return None

            text = self._render_context(record)

            return ProjectDNAContext(
                workspace_path=normalized,
                source_file=PROJECT_DNA_FILENAME,
                project_id=record.project_id,
                revision=record.revision,
                digest=record.digest,
                text=text,
                chars=len(text),
            )

    def _request_fingerprint(
        self,
        *,
        workspace_path: str,
        idempotency_key_hash: str,
        content: ProjectDNAContent,
    ) -> str:
        return _canonical_digest(
            {
                "workspace_path": workspace_path,
                "idempotency_key_hash": (
                    idempotency_key_hash
                ),
                "content": content.model_dump(
                    mode="json"
                ),
            }
        )

    def _atomic_write(
        self,
        *,
        path: Path,
        document: dict[str, Any],
    ) -> None:
        payload = _canonical_json_bytes(document)

        if len(payload) > self.max_file_bytes:
            raise ProjectDNAValidationError(
                "Project DNA document exceeds its size limit."
            )

        temporary = path.with_name(
            f".{PROJECT_DNA_FILENAME}."
            f"{secrets.token_hex(8)}.tmp"
        )

        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())

            os.replace(temporary, path)
        except OSError as exc:
            raise ProjectDNAError(
                "Project DNA source could not be written."
            ) from exc
        finally:
            try:
                if temporary.exists():
                    temporary.unlink()
            except OSError:
                pass

    def update(
        self,
        request: ProjectDNAUpdateRequest,
    ) -> ProjectDNAResponse:
        with self._lock:
            if not self.enabled:
                raise ProjectDNAValidationError(
                    "Project DNA is disabled."
                )

            (
                workspace_path,
                project_root,
                current,
            ) = self._read_record(
                request.workspace_path
            )

            content = _normalize_content(
                request.content,
                project_root=project_root,
                max_file_bytes=self.max_file_bytes,
                max_search_results=(
                    self.max_search_results
                ),
            )

            idempotency_key = (
                request.idempotency_key.strip()
            )

            if len(idempotency_key) < 8:
                raise ProjectDNAValidationError(
                    "Idempotency key is invalid."
                )

            idempotency_key_hash = _sha256_text(
                idempotency_key
            )

            fingerprint = (
                self._request_fingerprint(
                    workspace_path=workspace_path,
                    idempotency_key_hash=(
                        idempotency_key_hash
                    ),
                    content=content,
                )
            )

            if (
                current is not None
                and hmac.compare_digest(
                    current.last_idempotency_key_hash,
                    idempotency_key_hash,
                )
            ):
                if not hmac.compare_digest(
                    current.last_update_fingerprint,
                    fingerprint,
                ):
                    raise ProjectDNAConflictError(
                        "Project DNA idempotency key was reused with different content."
                    )

                return self._response(
                    workspace_path=workspace_path,
                    record=current,
                    replayed=True,
                    side_effect_free=False,
                )

            if current is None:
                if (
                    request.expected_revision != 0
                    or request.expected_digest
                    is not None
                ):
                    raise ProjectDNAConflictError(
                        "Project DNA creation precondition failed."
                    )

                project_id = (
                    "pdna_" + secrets.token_hex(16)
                )
                revision = 1
                created = True
                updated = False
            else:
                if (
                    request.expected_revision
                    != current.revision
                ):
                    raise ProjectDNAConflictError(
                        "Project DNA revision conflict."
                    )

                if request.expected_digest is None:
                    raise ProjectDNAConflictError(
                        "Project DNA digest is required for updates."
                    )

                if not hmac.compare_digest(
                    request.expected_digest,
                    current.digest,
                ):
                    raise ProjectDNAConflictError(
                        "Project DNA digest conflict."
                    )

                project_id = current.project_id
                revision = current.revision + 1
                created = False
                updated = True

            document: dict[str, Any] = {
                "schema_version": (
                    PROJECT_DNA_SCHEMA_VERSION
                ),
                "project_id": project_id,
                "revision": revision,
                "updated_at": _utc_now(),
                "last_idempotency_key_hash": (
                    idempotency_key_hash
                ),
                "last_update_fingerprint": (
                    fingerprint
                ),
                "content": content.model_dump(
                    mode="json"
                ),
            }

            path = self._dna_path(project_root)

            if path.is_symlink():
                raise ProjectDNAIntegrityError(
                    "Project DNA source is invalid."
                )

            self._atomic_write(
                path=path,
                document=document,
            )

            (
                verified_workspace_path,
                _verified_root,
                verified_record,
            ) = self._read_record(
                workspace_path
            )

            if verified_record is None:
                raise ProjectDNAIntegrityError(
                    "Project DNA write verification failed."
                )

            return self._response(
                workspace_path=(
                    verified_workspace_path
                ),
                record=verified_record,
                created=created,
                updated=updated,
                side_effect_free=False,
            )
