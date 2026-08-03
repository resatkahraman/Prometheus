from app.planning.integrity import validate_planning_document
from app.planning.parser import parse_planning_document


def wrap(block: str) -> str:
    return f"""
## Doğrulanmış Proje Gerçekleri
- [file:app.py] Python dosyası mevcut.

## Varsayımlar
- Yok

## Görevler
{block}

## Kritik Kullanıcı Kararları
- Yok
"""


BASE = """
### TASK-001 — Python fonksiyonunu test et
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
"""


def validate(block: str):
    return validate_planning_document(
        parse_planning_document(wrap(block)),
        known_paths={"app.py"},
        known_agents={
            "planner",
            "architect",
            "qa",
            "backend",
            "frontend",
            "reviewer",
        },
    )


def test_planner_cannot_receive_generic_inspection_task():
    bad = BASE.replace(
        "Python fonksiyonunu test et",
        "Proje yapısını incele",
    ).replace(
        "Atanan Agent: qa",
        "Atanan Agent: planner",
    )
    result = validate(bad)
    assert result.valid is False
    assert any("Planner'a" in item for item in result.errors)


def test_working_claim_needs_real_runtime_verification():
    bad = BASE.replace(
        "pytest komutu exit code 0 ile tamamlanmalı.",
        "Topla fonksiyonu çalışır durumda olmalıdır.",
    ).replace(
        "Doğrulama: python -m pytest -q",
        "Doğrulama: workspace_read aracı",
    )
    result = validate(bad)
    assert result.valid is False
    assert any("çalışırlık" in item for item in result.errors)


def test_generic_project_structure_dependency_is_rejected():
    task_2 = BASE.replace("TASK-001", "TASK-002", 1).replace(
        "Bağımlılıklar: yok",
        "Bağımlılıklar: TASK-001",
    ).replace(
        "Bağımlılık Gerekçesi: yok",
        "Bağımlılık Gerekçesi: Proje yapısının belirlenmesi gerekli",
    )
    result = validate(BASE + task_2)
    assert result.valid is False
    assert any(
        "teknik olarak açıklayıcı değil" in item
        for item in result.errors
    )
