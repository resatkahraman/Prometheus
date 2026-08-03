import pytest

from app.planning.parser import PlanningParseError, parse_planning_document


VALID = """
## Doğrulanmış Proje Gerçekleri
- [file:app.py] Python dosyası mevcut.

## Varsayımlar
- Yok

## Görevler
### TASK-001 — Python testlerini oluştur
Seviye: zorunlu
Atanan Agent: qa
Kanıt: file:app.py
Kabul Kriterleri:
- pytest komutu exit code 0 ile tamamlanmalı.
- Pozitif ve negatif girdiler test edilmeli.
Bağımlılıklar: yok
Bağımlılık Gerekçesi: yok
Paralel Çalışabilir: evet
Doğrulama: python -m pytest -q
Kullanıcı Onayı: gerekmez
Kesin Dosyalar: yok

## Kritik Kullanıcı Kararları
- Yok
"""


def test_parse_valid_plan():
    document = parse_planning_document(VALID)
    assert len(document.tasks) == 1
    task = document.tasks[0]
    assert task.id == "TASK-001"
    assert task.assigned_agent == "qa"
    assert task.evidence[0].type == "file"
    assert task.evidence[0].value == "app.py"
    assert task.dependencies == []


def test_missing_required_field_fails():
    invalid = VALID.replace("Doğrulama: python -m pytest -q\n", "")
    with pytest.raises(PlanningParseError):
        parse_planning_document(invalid)
