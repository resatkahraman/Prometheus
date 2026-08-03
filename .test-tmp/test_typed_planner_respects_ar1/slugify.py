import re
import unicodedata


_TURKISH = str.maketrans({
    "ı": "i", "İ": "i", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ş": "s", "Ş": "s",
    "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
})


def slugify(value: str) -> str:
    value = value.translate(_TURKISH).lower().strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")
