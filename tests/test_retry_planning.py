import asyncio
from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentResponse
from app.supervisor.models import SupervisorCommand
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


class GoodPlanner:
    async def run(self, request):
        return AgentResponse(
            answer=PLAN,
            agent_id="planner",
            agent_name="Planner",
            status="completed",
            steps_used=1,
            model_calls_used=1,
            tools_used=[],
            trace=[],
            final_route="groq_strong",
        )


@pytest.mark.asyncio
async def test_failed_command_can_retry_planning(tmp_path: Path):
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=GoodPlanner(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    command = SupervisorCommand(
        id="retry-cmd",
        goal="Test altyapısı kur",
        status="failed",
        plan_text="",
        tasks=[],
        failure_reason="old failure",
    )
    await service.store.put(command)

    command = await service.retry_planning(
        command_id=command.id,
        background=True,
    )
    assert command.status == "planning"

    for _ in range(50):
        await asyncio.sleep(0.01)
        command = await service.get(command.id)
        if command.status != "planning":
            break

    assert command.status == "ready"
    assert command.failure_reason is None
    assert command.tasks[0].status == "ready"
