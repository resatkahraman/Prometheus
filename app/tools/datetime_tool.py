from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.tools.base import BaseTool, ToolError


_TIMEZONE_ALIASES = {
    "istanbul": "Europe/Istanbul",
    "İstanbul": "Europe/Istanbul",
    "turkey": "Europe/Istanbul",
    "türkiye": "Europe/Istanbul",
    "turkiye": "Europe/Istanbul",
    "tr": "Europe/Istanbul",
    "utc": "UTC",
    "gmt": "UTC",
}

_WEEKDAYS_TR = {
    0: "Pazartesi",
    1: "Salı",
    2: "Çarşamba",
    3: "Perşembe",
    4: "Cuma",
    5: "Cumartesi",
    6: "Pazar",
}


class CurrentDateTimeTool(BaseTool):
    name = "current_datetime"
    description = (
        "Belirtilen IANA saat dilimindeki güncel tarih ve saati verir. "
        "Kullanıcının verdiği saat dilimi aynen kullanılmalıdır. "
        "Örnek: Europe/Istanbul."
    )
    parameters = {
        "type": "object",
        "properties": {
            "timezone": {
                "type": "string",
                "description": (
                    "Zorunlu IANA saat dilimi. Örnek: Europe/Istanbul. "
                    "Kullanıcı İstanbul veya Türkiye derse Europe/Istanbul kullan."
                ),
            }
        },
        "required": ["timezone"],
        "additionalProperties": False,
    }

    @staticmethod
    def normalize_timezone(value: str) -> str:
        stripped = value.strip()
        lowered = stripped.casefold()
        for alias, canonical in _TIMEZONE_ALIASES.items():
            if lowered == alias.casefold():
                return canonical
        return stripped

    async def execute(self, arguments: dict[str, Any]) -> Any:
        timezone_value = arguments.get("timezone")
        if not isinstance(timezone_value, str) or not timezone_value.strip():
            raise ToolError(
                "'timezone' zorunludur. Örnek: Europe/Istanbul."
            )

        timezone_name = self.normalize_timezone(timezone_value)

        try:
            zone = (
                timezone.utc
                if timezone_name.upper() == "UTC"
                else ZoneInfo(timezone_name)
            )
        except ZoneInfoNotFoundError as exc:
            raise ToolError(
                f"Bilinmeyen IANA saat dilimi: {timezone_name}. "
                "Windows kurulumunda tzdata paketinin kurulu olduğundan emin ol."
            ) from exc

        now = datetime.now(zone)
        offset = now.utcoffset()
        offset_seconds = int(offset.total_seconds()) if offset else 0
        sign = "+" if offset_seconds >= 0 else "-"
        offset_seconds = abs(offset_seconds)
        offset_hours, remainder = divmod(offset_seconds, 3600)
        offset_minutes = remainder // 60

        return {
            "timezone": timezone_name,
            "iso": now.isoformat(),
            "date": now.date().isoformat(),
            "time": now.strftime("%H:%M:%S"),
            "weekday": _WEEKDAYS_TR[now.weekday()],
            "utc_offset": (
                f"{sign}{offset_hours:02d}:{offset_minutes:02d}"
            ),
        }
