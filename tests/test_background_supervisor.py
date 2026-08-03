import asyncio
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentResponse
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


PLAN = """## Doğrulanmış Proje Gerçekleri
- [file:app.py] Python dosyası mevcut.

## Varsayımlar
- Yok

## Görevler
### TASK-001 — Python testlerini oluştur
Seviye: zorunlu
Atanan Agent: qa
Kanıt: file:app.py
Kabul Kriterleri:
- pytest exit code 0 ile tamamlanmalı.
Bağımlılıklar: yok
Bağımlılık Gerekçesi: yok
Paralel Çalışabilir: evet
Doğrulama: python -m pytest -q
Kullanıcı Onayı: gerekmez
Kesin Dosyalar: yok

## Kritik Kullanıcı Kararları
- Yok"""


class SlowPlanner:
    async def run(self, request):
        await asyncio.sleep(0.03)
        return AgentResponse(
            answer=PLAN,
            agent_id="planner",
            agent_name="Planner",
            status="completed",
            steps_used=1,
            model_calls_used=1,
            tools_used=[],
            trace=[],
        )


@pytest.mark.asyncio
async def test_background_create_returns_planning_then_updates(tmp_path: Path):
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=SlowPlanner(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    command = await service.create(
        goal="Testleri kur",
        background=True,
    )
    assert command.status == "planning"

    for _ in range(30):
        await asyncio.sleep(0.01)
        command = await service.get(command.id)
        if command.status != "planning":
            break

    assert command.status == "ready"
    assert command.tasks[0].status == "ready"
