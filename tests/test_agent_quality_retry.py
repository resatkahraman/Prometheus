from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.tools.registry import build_default_tool_registry


VALID_PLAN = """## Doğrulanmış Proje Gerçekleri
- [file:app.py] Python dosyası mevcut.

## Varsayımlar
- Yok

## Görevler
### TASK-001 — Python birim testlerini oluştur
Seviye: zorunlu
Atanan Agent: qa
Kanıt: file:app.py
Kabul Kriterleri:
- pytest komutu exit code 0 ile tamamlanmalı.
Bağımlılıklar: yok
Bağımlılık Gerekçesi: yok
Paralel Çalışabilir: evet
Doğrulama: python -m pytest -q
Kullanıcı Onayı: gerekmez
Kesin Dosyalar: yok

## Kritik Kullanıcı Kararları
- Yok"""


class PlannerOrchestrator:
    def __init__(self):
        self.calls = 0
        self.requests = []

    async def run(self, request):
        self.calls += 1
        self.requests.append(request)
        if self.calls == 1:
            answer = (
                '{"action":"final","reason":"Hazır.",'
                '"answer":"Görev listesi ve bağımlılıkları tanımlandı."}'
            )
            route = "groq_strong"
        else:
            import json
            answer = json.dumps(
                {
                    "action": "final",
                    "reason": "Eksiksiz teslim.",
                    "answer": VALID_PLAN,
                },
                ensure_ascii=False,
            )
            route = "gemini"

        return OrchestrateResponse(
            answer=answer,
            mode="auto",
            selected_route=route,
            selected_provider="test",
            model="test",
            latency_ms=1,
            task_type="reasoning",
            route_reason="test",
            calls_used=1,
            routing_scores=[],
        )


@pytest.mark.asyncio
async def test_planner_invalid_plan_is_retried(tmp_path: Path):
    (tmp_path / "app.py").write_text(
        "def topla(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    settings = Settings(
        workspace_root=tmp_path,
        agent_max_steps=8,
        agent_max_model_calls=6,
        agent_quality_max_retries=2,
    )
    orchestrator = PlannerOrchestrator()
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=build_default_tool_registry(settings=settings),
    )

    result = await engine.run(
        AgentRequest(
            message="Projeyi görevlere ayır.",
            agent_id="planner",
        )
    )

    assert result.status == "completed"
    assert result.model_calls_used == 2
    assert "TASK-001" in result.answer
    assert any(
        step.action == "quality_rejected"
        for step in result.trace
    )
