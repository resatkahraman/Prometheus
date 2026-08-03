from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.schemas import ChatMessage


@dataclass(slots=True)
class ProviderRequest:
    messages: list[ChatMessage]
    system_prompt: str
    temperature: float
    max_output_tokens: int
    model: str | None = None
    usage_scope: str | None = None
    usage_task_id: str | None = None
    local: bool = False


@dataclass(slots=True)
class ProviderResponse:
    provider: str
    model: str
    content: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_usage: dict[str, Any] | None = None
    rate_limit: dict[str, int | str | None] | None = None
    finish_reason: str | None = None


class AIProvider(ABC):
    name: str
    default_model: str

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        default_model: str,
        max_retries: int,
    ) -> None:
        self.client = client
        self.default_model = default_model
        self.max_retries = max_retries

    @abstractmethod
    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        raise NotImplementedError
