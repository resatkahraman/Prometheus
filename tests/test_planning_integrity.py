from app.planning.integrity import validate_planning_document
from app.planning.parser import parse_planning_document


def plan(task_blocks: str) -> str:
    return f"""
## Doğrulanmış Proje Gerçekleri
- [file:app.py] Python dosyası mevcut.

## Varsayımlar
- Yok

## Görevler
{task_blocks}

## Kritik Kullanıcı Kararları
- Yok
"""


TASK_1 = """
### TASK-001 — Python testlerini oluştur
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


def test_valid_plan_builds_execution_layers():
    document = parse_planning_document(plan(TASK_1))
    result = validate_planning_document(
        document,
        known_paths={"app.py"},
        known_agents={"qa", "worker"},
    )
    assert result.valid is True
    assert result.execution_layers == [["TASK-001"]]


def test_unknown_evidence_file_fails():
    bad = TASK_1.replace("file:app.py", "file:missing.py")
    document = parse_planning_document(plan(bad))
    result = validate_planning_document(
        document,
        known_paths={"app.py"},
        known_agents={"qa"},
    )
    assert result.valid is False
    assert any("bulunmayan dosya" in item for item in result.errors)


def test_assumption_cannot_be_mandatory():
    bad = TASK_1.replace(
        "Kanıt: file:app.py",
        "Kanıt: assumption:React kullanılacak",
    )
    document = parse_planning_document(plan(bad))
    result = validate_planning_document(
        document,
        known_paths={"app.py"},
        known_agents={"qa"},
    )
    assert result.valid is False
    assert any("varsayıma" in item for item in result.errors)


def test_dependency_cycle_fails():
    task_a = TASK_1.replace(
        "Bağımlılıklar: yok",
        "Bağımlılıklar: TASK-002",
    ).replace(
        "Bağımlılık Gerekçesi: yok",
        "Bağımlılık Gerekçesi: TASK-002 çıktısı test girdisini belirler.",
    )
    task_b = TASK_1.replace(
        "TASK-001",
        "TASK-002",
        1,
    ).replace(
        "Python testlerini oluştur",
        "Entegrasyonu doğrula",
    ).replace(
        "Bağımlılıklar: yok",
        "Bağımlılıklar: TASK-001",
    ).replace(
        "Bağımlılık Gerekçesi: yok",
        "Bağımlılık Gerekçesi: TASK-001 testleri entegrasyon öncesi geçmelidir.",
    )
    document = parse_planning_document(plan(task_a + task_b))
    result = validate_planning_document(
        document,
        known_paths={"app.py"},
        known_agents={"qa"},
    )
    assert result.valid is False
    assert any("döngü" in item for item in result.errors)


def test_delete_requires_exact_files_and_approval():
    bad = TASK_1.replace(
        "Python testlerini oluştur",
        "Gereksiz dosyaları sil",
    ).replace(
        "Kullanıcı Onayı: gerekmez",
        "Kullanıcı Onayı: gerekmez",
    )
    document = parse_planning_document(plan(bad))
    result = validate_planning_document(
        document,
        known_paths={"app.py"},
        known_agents={"qa"},
    )
    assert result.valid is False
    assert any("kullanıcı onayı" in item for item in result.errors)
    assert any("Kesin Dosyalar" in item for item in result.errors)


def test_application_clear_and_backspace_are_not_workspace_deletion():
    calculator = TASK_1.replace(
        "Python testlerini oluştur",
        "Calculator için tek dosya statik web uygulamasını oluştur",
    ).replace(
        "pytest komutu exit code 0 ile tamamlanmalı.",
        "Temizle ve geri silme düğmeleri çalışmalı.",
    ).replace(
        "Kullanıcı Onayı: gerekmez",
        "Kullanıcı Onayı: gerekli",
    ).replace(
        "Kesin Dosyalar: yok",
        "Kesin Dosyalar: calculator.html",
    )
    document = parse_planning_document(plan(calculator))
    result = validate_planning_document(
        document,
        known_paths={"existing.html", "app.py"},
        known_agents={"qa", "worker"},
    )

    assert result.valid is True
    assert not any("silmek için bulunmayan" in item for item in result.errors)
