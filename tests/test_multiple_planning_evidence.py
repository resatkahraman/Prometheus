from app.planning.integrity import validate_planning_document
from app.planning.parser import parse_planning_document


PLAN = """
## Doğrulanmış Proje Gerçekleri
- [file:app.py] Python dosyası mevcut.
- [file:src/components/TestButton.tsx] React bileşeni mevcut.

## Varsayımlar
- Yok

## Görevler
### TASK-001 — Proje envanterini doğrula
Seviye: zorunlu
Atanan Agent: reviewer
Kanıt: file:app.py, file:src/components/TestButton.tsx
Kabul Kriterleri:
- Her iki dosya workspace listesinde açıkça gösterilmeli.
Bağımlılıklar: yok
Bağımlılık Gerekçesi: yok
Paralel Çalışabilir: evet
Doğrulama: workspace_list sonucu incelenmeli.
Kullanıcı Onayı: gerekmez
Kesin Dosyalar: yok

## Kritik Kullanıcı Kararları
- Yok
"""


def test_multiple_file_evidence_is_parsed_separately():
    document = parse_planning_document(PLAN)
    evidence = document.tasks[0].evidence
    assert len(evidence) == 2
    assert evidence[0].value == "app.py"
    assert evidence[1].value == "src/components/TestButton.tsx"


def test_multiple_file_evidence_validates():
    document = parse_planning_document(PLAN)
    result = validate_planning_document(
        document,
        known_paths={
            "app.py",
            "src/components/TestButton.tsx",
        },
        known_agents={"reviewer"},
    )
    assert result.valid is True
