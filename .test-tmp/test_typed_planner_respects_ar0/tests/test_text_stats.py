import pytest

from text_stats import top_words, word_count


def test_existing_word_count():
    assert word_count("one two three") == 3


def test_top_words_is_deterministic():
    assert top_words("Blue red blue GREEN green red blue", 2) == [
        ("blue", 3),
        ("green", 2),
    ]


def test_top_words_ignores_punctuation():
    assert top_words("Prometheus, prometheus! arena-2 arena2", 3) == [
        ("prometheus", 2),
        ("arena", 1),
        ("arena2", 1),
    ]


def test_top_words_validates_limit():
    with pytest.raises(ValueError):
        top_words("hello", 0)
