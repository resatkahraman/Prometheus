"""Autonomous TDD Self-Fix Loop Engine for Prometheus.

Captures test/verification failures, extracts empirical tracebacks,
and auto-generates replanning strategies for up to 5 self-healing retries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class TDDSelfFixMaxRetriesExceeded(Exception):
    """Raised when the maximum TDD self-fix retries (5) have been exhausted."""


@dataclass
class SelfFixAttempt:
    attempt: int
    error_message: str
    traceback_snippet: str
    timestamp: str
    replan_strategy: str


@dataclass
class TDDSelfFixLoop:
    command_id: str
    max_retries: int = 5
    current_attempt: int = 0
    history: list[SelfFixAttempt] = field(default_factory=list)

    def record_failure_and_generate_replan(
        self,
        error_message: str,
        traceback_snippet: str,
        timestamp: str,
    ) -> str:
        """Records a test/verification failure and returns an explicit replan directive."""
        self.current_attempt += 1
        if self.current_attempt > self.max_retries:
            raise TDDSelfFixMaxRetriesExceeded(
                f"Maksimum TDD self-fix hakkı ({self.max_retries}) aşıldı! Görev kilitlendi."
            )

        strategy = (
            f"[TDD SELF-FIX DÖNGÜSÜ - DENEME {self.current_attempt}/{self.max_retries}]\n"
            f"Test/Doğrulama Hatası: {error_message}\n"
            f"Hata İzleme (Traceback):\n{traceback_snippet}\n\n"
            f"TALİMAT: Aynı hatayı tekrarlama! Kök nedeni yukarıdaki traceback verisine göre düzelt, "
            f"ilgili dosyayı güncelle ve test paketini tekrar çalıştır."
        )

        attempt_record = SelfFixAttempt(
            attempt=self.current_attempt,
            error_message=error_message,
            traceback_snippet=traceback_snippet,
            timestamp=timestamp,
            replan_strategy=strategy,
        )
        self.history.append(attempt_record)
        return strategy
