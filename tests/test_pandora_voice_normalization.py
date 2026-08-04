from __future__ import annotations

from app.pandora_voice.normalization import (
    chunk_text,
    make_speak_text,
    normalize_for_tts,
    number_to_turkish,
)


def test_turkish_number_conversion() -> None:
    assert number_to_turkish(0) == "sıfır"
    assert number_to_turkish(2026) == "iki bin yirmi altı"
    assert number_to_turkish(478) == "dört yüz yetmiş sekiz"


def test_normalization_handles_dates_times_percent_paths_and_secrets() -> None:
    value = normalize_for_tts(
        "03.08.2026 saat 18:45, başarı %60. "
        r"C:\Users\Test\secret.txt ve https://example.com/path "
        "token=abcdefghijklmnopqrstuv"
    )
    assert "üç Ağustos iki bin yirmi altı" in value
    assert "on sekiz kırk beş" in value
    assert "yüzde altmış" in value
    assert "secret.txt" in value
    assert "example.com" in value
    assert "abcdefghijklmnopqrstuv" not in value
    assert "gizli değer" in value


def test_chunking_never_exceeds_hard_limit_for_unbroken_sentence() -> None:
    text = " ".join(["Pandora"] * 200)
    chunks = chunk_text(text, target_chars=80, hard_max_chars=120)
    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 120 for chunk in chunks)
    assert " ".join(chunks).replace("  ", " ") == text


def test_make_speak_text_bounds_long_answer() -> None:
    full = "Birinci cümle kısa. " + ("İkinci bölüm çok uzun " * 80)
    spoken = make_speak_text(full, max_speak_chars=100)
    assert spoken
    assert len(spoken) <= 130
