from __future__ import annotations

import hashlib
import math
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from threading import RLock
from typing import Callable, Literal

from fastapi import Request
from pydantic import BaseModel, Field, field_validator, model_validator


PANDORA_SESSION_COOKIE_NAME = "prometheus_pandora_session"
PANDORA_SESSION_COOKIE_PATH = "/v1/pandora"
PANDORA_PAIRING_TTL_SECONDS = 300
PANDORA_SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
PANDORA_MAX_DEVICES = 5
PANDORA_MAX_PAIRING_ATTEMPTS = 5

PANDORA_CHAT_MESSAGE_MAX_CHARS = 4_000
PANDORA_CHAT_HISTORY_MAX_MESSAGES = 12
PANDORA_CHAT_CONTEXT_MAX_CHARS = 16_000
PANDORA_CHAT_REQUESTS_PER_WINDOW = 10
PANDORA_CHAT_RATE_WINDOW_SECONDS = 60
PANDORA_CHAT_BUSY_RETRY_SECONDS = 2

PANDORA_PROJECT_RUN_GOAL_MAX_CHARS = 2_000
PANDORA_PROJECT_RUN_REQUESTS_PER_WINDOW = 6
PANDORA_PROJECT_RUN_RATE_WINDOW_SECONDS = 60
PANDORA_PROJECT_RUN_BUSY_RETRY_SECONDS = 2
PANDORA_PROJECT_RUN_PREVIEW_TTL_SECONDS = 10 * 60
PANDORA_PROJECT_RUN_MAX_TASKS = 24
PANDORA_PROJECT_RUN_MAX_FILES = 200
PANDORA_PROJECT_LIST_LIMIT = 50

PANDORA_PAIRING_REQUIRED_DETAIL = "Pandora eşleştirmesi gerekli."
PANDORA_PAIRING_INVALID_DETAIL = (
    "Eşleştirme kodu geçersiz, kullanılmış veya süresi dolmuş."
)
PANDORA_PAIRING_LOCAL_ONLY_DETAIL = (
    "Eşleştirme kodu yalnızca Prometheus'un çalıştığı bilgisayardan oluşturulabilir."
)
PANDORA_REMOTE_ACCESS_REQUIRED_DETAIL = (
    "Pandora eşleştirmesi için uzak HTTP erişimi etkin olmalı."
)
PANDORA_DEVICE_LIMIT_DETAIL = (
    "Pandora cihaz sınırına ulaşıldı. Yeni cihaz eşleştirmeden önce mevcut "
    "bir oturum kapatılmalı."
)
PANDORA_CHAT_BUSY_DETAIL = (
    "Pandora bu cihaz için hâlâ önceki yanıtı hazırlıyor."
)
PANDORA_CHAT_RATE_LIMIT_DETAIL = (
    "Pandora istek sınırına ulaşıldı. Kısa süre sonra yeniden dene."
)
PANDORA_CHAT_UNAVAILABLE_DETAIL = (
    "Pandora şu anda yanıt üretemiyor. Biraz sonra yeniden dene."
)
PANDORA_PROJECT_RUN_BUSY_DETAIL = (
    "Pandora bu cihaz için hâlâ önceki Project Run isteğini hazırlıyor."
)
PANDORA_PROJECT_RUN_RATE_LIMIT_DETAIL = (
    "Pandora Project Run istek sınırına ulaşıldı. Kısa süre sonra yeniden dene."
)
PANDORA_PROJECT_RUN_PREVIEW_REQUIRED_DETAIL = (
    "Bu Project Run planı bu cihazda oluşturulmamış, değiştirilmiş veya süresi dolmuş."
)
PANDORA_PROJECT_RUN_UNAVAILABLE_DETAIL = (
    "Project Run şu anda hazırlanamadı. Masaüstü Prometheus durumunu kontrol et."
)
PANDORA_PROJECT_RUN_NOT_FOUND_DETAIL = (
    "Project Run bu Pandora oturumu için bulunamadı."
)


class PandoraPairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    device_name: str = Field(default="Pandora cihazı", min_length=1, max_length=64)

    @field_validator("device_name")
    @classmethod
    def normalize_device_name(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        return normalized or "Pandora cihazı"


class PandoraChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=PANDORA_CHAT_MESSAGE_MAX_CHARS)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Mesaj boş olamaz.")
        return normalized


class PandoraChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=PANDORA_CHAT_MESSAGE_MAX_CHARS)
    history: list[PandoraChatMessage] = Field(
        default_factory=list,
        max_length=PANDORA_CHAT_HISTORY_MAX_MESSAGES,
    )

    @field_validator("message")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Mesaj boş olamaz.")
        return normalized

    @model_validator(mode="after")
    def validate_history(self) -> PandoraChatRequest:
        if len(self.history) % 2:
            raise ValueError(
                "Sohbet geçmişi tamamlanmış kullanıcı/asistan çiftlerinden oluşmalı."
            )

        for index, item in enumerate(self.history):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if item.role != expected_role:
                raise ValueError(
                    "Sohbet geçmişi kullanıcı ve asistan mesajlarıyla sırayla ilerlemeli."
                )

        total_chars = len(self.message) + sum(
            len(item.content) for item in self.history
        )
        if total_chars > PANDORA_CHAT_CONTEXT_MAX_CHARS:
            raise ValueError("Pandora sohbet bağlamı izin verilen sınırı aşıyor.")
        return self


class PandoraChatResponse(BaseModel):
    answer: str


class PandoraProjectSummary(BaseModel):
    name: str
    workspace_path: str
    project_types: list[str] = Field(default_factory=list)
    dirty: bool = False


class PandoraProjectsResponse(BaseModel):
    projects: list[PandoraProjectSummary] = Field(default_factory=list)
    truncated: bool = False


class PandoraProjectRunPreviewRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=PANDORA_PROJECT_RUN_GOAL_MAX_CHARS)
    workspace_path: str = Field(default=".", min_length=1, max_length=1000)

    @field_validator("goal")
    @classmethod
    def normalize_goal(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        if len(normalized) < 3:
            raise ValueError("Görev açıklaması en az 3 karakter olmalıdır.")
        return normalized

    @field_validator("workspace_path")
    @classmethod
    def normalize_workspace_path(cls, value: str) -> str:
        normalized = value.strip().replace("\\", "/") or "."
        parts = [part for part in normalized.split("/") if part not in {"", "."}]
        if (
            normalized.startswith("/")
            or ":" in normalized
            or "\x00" in normalized
            or any(part == ".." for part in parts)
        ):
            raise ValueError("Workspace yolu göreli ve güvenli olmalıdır.")
        return "/".join(parts) or "."


class PandoraProjectRunPreviewTask(BaseModel):
    title: str
    exact_files: list[str] = Field(default_factory=list)
    verification: str


class PandoraProjectRunPreviewResponse(BaseModel):
    goal: str
    workspace_path: str
    tasks: list[PandoraProjectRunPreviewTask]
    exact_files: list[str]
    task_count: int
    exact_file_count: int
    requires_approval: bool = True
    side_effect_free: bool = True
    preview_digest: str
    expires_in: int


class PandoraProjectRunCommitRequest(PandoraProjectRunPreviewRequest):
    preview_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class PandoraProjectRunCommitResponse(BaseModel):
    command_id: str
    status: str
    goal: str
    workspace_path: str
    task_count: int
    requires_desktop_approval: bool = True
    execution_started: bool = False
    created: bool


class PandoraProjectRunTaskStatus(BaseModel):
    title: str
    status: str
    approval_state: str | None = None
    exact_file_count: int = 0


class PandoraProjectRunStatusResponse(BaseModel):
    command_id: str
    goal: str
    workspace_path: str
    status: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    waiting_approval_tasks: int
    progress_percent: int
    requires_desktop_approval: bool
    terminal: bool
    tasks: list[PandoraProjectRunTaskStatus] = Field(default_factory=list)


class PandoraPairingRejectedError(RuntimeError):
    pass


class PandoraDeviceLimitError(RuntimeError):
    pass


class PandoraChatBusyError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(PANDORA_CHAT_BUSY_DETAIL)
        self.retry_after_seconds = retry_after_seconds


class PandoraChatRateLimitError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(PANDORA_CHAT_RATE_LIMIT_DETAIL)
        self.retry_after_seconds = retry_after_seconds


class PandoraProjectRunBusyError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(PANDORA_PROJECT_RUN_BUSY_DETAIL)
        self.retry_after_seconds = retry_after_seconds


class PandoraProjectRunRateLimitError(RuntimeError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(PANDORA_PROJECT_RUN_RATE_LIMIT_DETAIL)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class PandoraSessionInfo:
    device_name: str
    created_at: float
    expires_at: float


@dataclass
class _PairingCode:
    digest: bytes
    expires_at: float
    remaining_attempts: int


@dataclass
class _PandoraChatState:
    request_times: deque[float] = field(default_factory=deque)
    in_flight: bool = False


@dataclass
class _PandoraProjectRunState:
    request_times: deque[float] = field(default_factory=deque)
    in_flight: bool = False
    preview_digest: str | None = None
    preview_goal: str | None = None
    preview_workspace_path: str | None = None
    preview_expires_at: float = 0.0
    command_ids: list[str] = field(default_factory=list)


class PandoraSessionManager:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        pairing_ttl_seconds: int = PANDORA_PAIRING_TTL_SECONDS,
        session_ttl_seconds: int = PANDORA_SESSION_TTL_SECONDS,
        max_devices: int = PANDORA_MAX_DEVICES,
        max_pairing_attempts: int = PANDORA_MAX_PAIRING_ATTEMPTS,
        chat_requests_per_window: int = PANDORA_CHAT_REQUESTS_PER_WINDOW,
        chat_rate_window_seconds: int = PANDORA_CHAT_RATE_WINDOW_SECONDS,
        project_run_requests_per_window: int = PANDORA_PROJECT_RUN_REQUESTS_PER_WINDOW,
        project_run_rate_window_seconds: int = PANDORA_PROJECT_RUN_RATE_WINDOW_SECONDS,
        project_run_preview_ttl_seconds: int = PANDORA_PROJECT_RUN_PREVIEW_TTL_SECONDS,
    ) -> None:
        self._clock = clock
        self._pairing_ttl_seconds = pairing_ttl_seconds
        self._session_ttl_seconds = session_ttl_seconds
        self._max_devices = max_devices
        self._max_pairing_attempts = max_pairing_attempts
        self._chat_requests_per_window = chat_requests_per_window
        self._chat_rate_window_seconds = chat_rate_window_seconds
        self._project_run_requests_per_window = project_run_requests_per_window
        self._project_run_rate_window_seconds = project_run_rate_window_seconds
        self._project_run_preview_ttl_seconds = project_run_preview_ttl_seconds
        self._pairing_code: _PairingCode | None = None
        self._sessions: dict[bytes, PandoraSessionInfo] = {}
        self._chat_states: dict[bytes, _PandoraChatState] = {}
        self._project_run_states: dict[bytes, _PandoraProjectRunState] = {}
        self._lock = RLock()

    @property
    def pairing_ttl_seconds(self) -> int:
        return self._pairing_ttl_seconds

    @property
    def session_ttl_seconds(self) -> int:
        return self._session_ttl_seconds

    @property
    def project_run_preview_ttl_seconds(self) -> int:
        return self._project_run_preview_ttl_seconds

    @staticmethod
    def _digest(value: str) -> bytes:
        return hashlib.sha256(value.encode("utf-8")).digest()

    @staticmethod
    def _retry_after(
        request_times: deque[float],
        *,
        now: float,
        window_seconds: int,
    ) -> int:
        return max(
            1,
            math.ceil(request_times[0] + window_seconds - now),
        )

    def _cleanup_locked(self, now: float) -> None:
        if self._pairing_code and self._pairing_code.expires_at <= now:
            self._pairing_code = None
        expired = [
            digest
            for digest, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for digest in expired:
            self._sessions.pop(digest, None)
            self._chat_states.pop(digest, None)
            self._project_run_states.pop(digest, None)

        for state in self._project_run_states.values():
            if state.preview_digest and state.preview_expires_at <= now:
                state.preview_digest = None
                state.preview_goal = None
                state.preview_workspace_path = None
                state.preview_expires_at = 0.0

    def issue_pairing_code(self) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = self._clock()
        with self._lock:
            self._cleanup_locked(now)
            self._pairing_code = _PairingCode(
                digest=self._digest(code),
                expires_at=now + self._pairing_ttl_seconds,
                remaining_attempts=self._max_pairing_attempts,
            )
        return code

    def create_session(self, *, code: str, device_name: str) -> str:
        now = self._clock()
        normalized_code = code.strip()
        with self._lock:
            self._cleanup_locked(now)
            pairing = self._pairing_code
            if pairing is None:
                raise PandoraPairingRejectedError(
                    PANDORA_PAIRING_INVALID_DETAIL
                )

            pairing.remaining_attempts -= 1
            candidate_digest = self._digest(normalized_code)
            valid = secrets.compare_digest(
                candidate_digest,
                pairing.digest,
            )
            if not valid:
                if pairing.remaining_attempts <= 0:
                    self._pairing_code = None
                raise PandoraPairingRejectedError(
                    PANDORA_PAIRING_INVALID_DETAIL
                )

            self._pairing_code = None
            if len(self._sessions) >= self._max_devices:
                raise PandoraDeviceLimitError(PANDORA_DEVICE_LIMIT_DETAIL)

            token = secrets.token_urlsafe(32)
            token_digest = self._digest(token)
            self._sessions[token_digest] = PandoraSessionInfo(
                device_name=device_name,
                created_at=now,
                expires_at=now + self._session_ttl_seconds,
            )
            self._chat_states[token_digest] = _PandoraChatState()
            self._project_run_states[token_digest] = _PandoraProjectRunState()
            return token

    def session_for_token(self, token: str | None) -> PandoraSessionInfo | None:
        if not token:
            return None
        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            return self._sessions.get(digest)

    def begin_chat_request(
        self,
        token: str | None,
    ) -> PandoraSessionInfo | None:
        if not token:
            return None

        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            session = self._sessions.get(digest)
            if session is None:
                return None

            state = self._chat_states.setdefault(
                digest,
                _PandoraChatState(),
            )
            if state.in_flight:
                raise PandoraChatBusyError(PANDORA_CHAT_BUSY_RETRY_SECONDS)

            cutoff = now - self._chat_rate_window_seconds
            while state.request_times and state.request_times[0] <= cutoff:
                state.request_times.popleft()

            if len(state.request_times) >= self._chat_requests_per_window:
                raise PandoraChatRateLimitError(
                    self._retry_after(
                        state.request_times,
                        now=now,
                        window_seconds=self._chat_rate_window_seconds,
                    )
                )

            state.request_times.append(now)
            state.in_flight = True
            return session

    def end_chat_request(self, token: str | None) -> None:
        if not token:
            return
        digest = self._digest(token)
        with self._lock:
            state = self._chat_states.get(digest)
            if state is not None:
                state.in_flight = False

    def begin_project_run_request(
        self,
        token: str | None,
    ) -> PandoraSessionInfo | None:
        if not token:
            return None

        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            session = self._sessions.get(digest)
            if session is None:
                return None

            state = self._project_run_states.setdefault(
                digest,
                _PandoraProjectRunState(),
            )
            if state.in_flight:
                raise PandoraProjectRunBusyError(
                    PANDORA_PROJECT_RUN_BUSY_RETRY_SECONDS
                )

            cutoff = now - self._project_run_rate_window_seconds
            while state.request_times and state.request_times[0] <= cutoff:
                state.request_times.popleft()

            if len(state.request_times) >= self._project_run_requests_per_window:
                raise PandoraProjectRunRateLimitError(
                    self._retry_after(
                        state.request_times,
                        now=now,
                        window_seconds=self._project_run_rate_window_seconds,
                    )
                )

            state.request_times.append(now)
            state.in_flight = True
            return session

    def end_project_run_request(self, token: str | None) -> None:
        if not token:
            return
        digest = self._digest(token)
        with self._lock:
            state = self._project_run_states.get(digest)
            if state is not None:
                state.in_flight = False

    def remember_project_run_preview(
        self,
        token: str | None,
        *,
        preview_digest: str,
        goal: str,
        workspace_path: str,
    ) -> bool:
        if not token:
            return False
        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            if digest not in self._sessions:
                return False
            state = self._project_run_states.setdefault(
                digest,
                _PandoraProjectRunState(),
            )
            state.preview_digest = preview_digest
            state.preview_goal = goal
            state.preview_workspace_path = workspace_path
            state.preview_expires_at = now + self._project_run_preview_ttl_seconds
            return True

    def project_run_preview_is_valid(
        self,
        token: str | None,
        *,
        preview_digest: str,
        goal: str,
        workspace_path: str,
    ) -> bool:
        if not token:
            return False
        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            state = self._project_run_states.get(digest)
            return bool(
                state is not None
                and state.preview_digest == preview_digest
                and state.preview_goal == goal
                and state.preview_workspace_path == workspace_path
                and state.preview_expires_at > now
            )

    def register_project_run(
        self,
        token: str | None,
        command_id: str,
    ) -> bool:
        if not token:
            return False
        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            if digest not in self._sessions:
                return False
            state = self._project_run_states.setdefault(
                digest,
                _PandoraProjectRunState(),
            )
            if command_id not in state.command_ids:
                state.command_ids.append(command_id)
            return True

    def latest_project_run_id(self, token: str | None) -> str | None:
        if not token:
            return None
        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            state = self._project_run_states.get(digest)
            if state is None or not state.command_ids:
                return None
            return state.command_ids[-1]

    def owns_project_run(
        self,
        token: str | None,
        command_id: str,
    ) -> bool:
        if not token:
            return False
        now = self._clock()
        digest = self._digest(token)
        with self._lock:
            self._cleanup_locked(now)
            state = self._project_run_states.get(digest)
            return bool(state is not None and command_id in state.command_ids)

    def revoke(self, token: str | None) -> bool:
        if not token:
            return False
        digest = self._digest(token)
        with self._lock:
            self._chat_states.pop(digest, None)
            self._project_run_states.pop(digest, None)
            return self._sessions.pop(digest, None) is not None

    def active_session_count(self) -> int:
        now = self._clock()
        with self._lock:
            self._cleanup_locked(now)
            return len(self._sessions)


def request_pandora_session_token(request: Request) -> str | None:
    token = request.cookies.get(PANDORA_SESSION_COOKIE_NAME)
    return token.strip() if token else None
