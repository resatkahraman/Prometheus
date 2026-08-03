from __future__ import annotations

import httpx


class OllamaEmbeddingClient:
    """Small optional embedding client; callers always retain lexical fallback."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/api/embed",
                json={
                    "model": self.model,
                    "input": texts,
                    "truncate": True,
                    "keep_alive": "10m",
                    # Keep the coding model on the GPU. Embedding is background
                    # optimization and must not evict the primary local model.
                    "options": {"num_gpu": 0},
                },
            )
            response.raise_for_status()
            payload = response.json()
        embeddings = payload.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("Ollama embedding response shape is invalid.")
        return [
            [float(value) for value in vector]
            for vector in embeddings
            if isinstance(vector, list)
        ]
