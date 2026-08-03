from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field


CandidateKind = Literal[
    "strategy",
    "prompt_delta",
    "router_policy",
    "source_patch",
]


@dataclass(frozen=True)
class RecallCapsule:
    text: str
    task_signature: str
    strategy_ids: list[str] = field(default_factory=list)
    orientation_ids: list[str] = field(default_factory=list)
    chars: int = 0
    lexical_only: bool = True


class RecallRequest(BaseModel):
    query: str = Field(min_length=2, max_length=8_000)
    target_path: str | None = Field(default=None, max_length=500)
    max_chars: int | None = Field(default=None, ge=300, le=8_000)


class CandidateCreateRequest(BaseModel):
    kind: CandidateKind = "strategy"
    title: str = Field(min_length=3, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)


class CandidatePromoteRequest(BaseModel):
    confirmation: str = Field(min_length=3, max_length=100)


class BenchmarkRunRequest(BaseModel):
    candidate_id: str | None = Field(default=None, max_length=80)
