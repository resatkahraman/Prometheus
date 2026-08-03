from app.agents.quality import inspect_agent_answer
from app.agents.registry import build_default_agent_registry
from app.tools.registry import build_default_tool_registry


def agents():
    tools = build_default_tool_registry()
    return build_default_agent_registry(tools.names())


STRICT_PLAN = """
## Doğrulanmış Proje Gerçekleri
- [file:app.py] Python dosyası mevcut.

## Varsayımlar
- Yok

## Görevler
### TASK-001 — Fonksiyon tiplerini tanımla
Seviye: önerilen
Atanan Agent: backend
Kanıt: file:app.py
Kabul Kriterleri:
- app.py içindeki parametre ve dönüş tipleri açıkça tanımlanmalı.
Bağımlılıklar: yok
Bağımlılık Gerekçesi: yok
Paralel Çalışabilir: evet
Doğrulama: python -m compileall -q .
Kullanıcı Onayı: gerekmez
Kesin Dosyalar: yok

### TASK-002 — Birim testlerini ekle
Seviye: zorunlu
Atanan Agent: qa
Kanıt: file:app.py
Kabul Kriterleri:
- Pozitif, negatif ve sıfır senaryolarını içeren pytest testleri exit code 0 ile tamamlanmalı.
Bağımlılıklar: yok
Bağımlılık Gerekçesi: yok
Paralel Çalışabilir: evet
Doğrulama: python -m pytest -q
Kullanıcı Onayı: gerekmez
Kesin Dosyalar: yok

## Kritik Kullanıcı Kararları
- Yok
"""


def test_planner_rejects_vague_completion():
    result = inspect_agent_answer(
        profile=agents().get("planner"),
        answer="Görev listesi ve bağımlılıkları tanımlandı.",
        user_text="Projeyi görevlere ayır.",
        known_paths={"app.py"},
        known_agents=set(agents().ids()),
    )
    assert result.accepted is False


def test_planner_accepts_complete_delivery():
    result = inspect_agent_answer(
        profile=agents().get("planner"),
        answer=STRICT_PLAN,
        user_text="Projeyi görevlere ayır.",
        known_paths={"app.py"},
        known_agents=set(agents().ids()),
    )
    assert result.accepted is True


def test_architect_requires_transition_plan():
    result = inspect_agent_answer(
        profile=agents().get("architect"),
        answer=(
            "Mevcut durum tek Python dosyasıdır. Mimari modüler değildir. "
            "Riskler test eksikliği ve büyüme problemidir. Önerilen hedef "
            "mimari servis ve test modülleridir."
        ),
        user_text="Mimariyi açıkla.",
    )
    assert result.accepted is False
