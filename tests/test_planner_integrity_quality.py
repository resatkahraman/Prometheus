from app.agents.quality import inspect_agent_answer
from app.agents.registry import build_default_agent_registry
from app.tools.registry import build_default_tool_registry


VALID = """
## Doğrulanmış Proje Gerçekleri
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
- Yok
"""


def planner():
    tools = build_default_tool_registry()
    return build_default_agent_registry(tools.names()).get("planner")


def test_planner_integrity_accepts_valid_plan():
    result = inspect_agent_answer(
        profile=planner(),
        answer=VALID,
        user_text="Planla",
        known_paths={"app.py"},
        known_agents={"planner", "qa", "worker"},
    )
    assert result.accepted is True


def test_planner_integrity_rejects_old_freeform_answer():
    result = inspect_agent_answer(
        profile=planner(),
        answer=(
            "Gereksinimler: test yaz. Görev 1: Test yaz. "
            "Kabul kriterleri: başarılı. Bağımlılık: yok. "
            "Kullanıcı kararları: yok."
        ),
        user_text="Planla",
        known_paths={"app.py"},
        known_agents={"planner", "qa"},
    )
    assert result.accepted is False
    assert "ayrıştırılamadı" in result.reason
