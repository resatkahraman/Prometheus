import httpx
import pytest

from app.core.schemas import ChatMessage
from app.providers.base import ProviderRequest
from app.providers.groq import GroqProvider


@pytest.mark.asyncio
async def test_groq_provider_parses_response_and_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Merhaba"}}
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
            },
            headers={
                "x-ratelimit-limit-requests": "1000",
                "x-ratelimit-remaining-requests": "999",
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        provider = GroqProvider(
            client=client,
            api_key="test",
            base_url="https://api.groq.com/openai/v1",
            default_model="llama-3.1-8b-instant",
            max_retries=0,
        )
        result = await provider.generate(
            ProviderRequest(
                messages=[
                    ChatMessage(role="user", content="Selam")
                ],
                system_prompt="Yardımcı ol.",
                temperature=0.2,
                max_output_tokens=100,
                model="llama-3.3-70b-versatile",
            )
        )

    assert result.content == "Merhaba"
    assert result.model == "llama-3.3-70b-versatile"
    assert result.rate_limit["requests_remaining"] == 999
