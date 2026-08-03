from app.planning.normalizer import normalize_planning_markdown
from app.planning.parser import parse_planning_document


BOLD_PLAN = """
## **Doğrulanmış Proje Gerçekleri**
- [file:app.py] Python dosyası mevcut.

## **Varsayımlar**
- Yok

## **Görevler**
**TASK-001: Python testlerini oluştur**
- **Seviye:** zorunlu
- **Atanan Agent:** qa
- **Kanıt:** file:app.py
- **Kabul Kriterleri:**
  - pytest komutu exit code 0 ile tamamlanmalı.
- **Bağımlılıklar:** yok
- **Bağımlılık Gerekçesi:** yok
- **Paralel Çalışabilir:** evet
- **Doğrulama:** python -m pytest -q
- **Kullanıcı Onayı:** gerekmez
- **Kesin Dosyalar:** yok

## **Kritik Kullanıcı Kararları**
- Yok
"""


def test_bold_bulleted_plan_normalizes():
    normalized = normalize_planning_markdown(BOLD_PLAN)
    assert "### TASK-001 — Python testlerini oluştur" in normalized
    assert "Seviye: zorunlu" in normalized
    assert "Atanan Agent: qa" in normalized
    assert "Kabul Kriterleri:" in normalized


def test_bold_bulleted_plan_parses():
    document = parse_planning_document(BOLD_PLAN)
    assert document.tasks[0].id == "TASK-001"
    assert document.tasks[0].assigned_agent == "qa"
    assert document.tasks[0].acceptance_criteria == [
        "pytest komutu exit code 0 ile tamamlanmalı."
    ]
