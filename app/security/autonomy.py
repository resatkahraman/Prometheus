from __future__ import annotations

from typing import Any


TRUSTED_AUTONOMY_DISABLED_DETAIL = (
    "Trusted otonomi sunucu yapılandırmasında devre dışı. "
    "Etkinleştirmek için SUPERVISOR_TRUSTED_AUTONOMY_ENABLED=true "
    "ayarını bilinçli olarak yapılandırın."
)


class TrustedAutonomyDisabledError(PermissionError):
    """Raised when a caller requests trusted autonomy without server opt-in."""


def trusted_autonomy_enabled(settings: Any) -> bool:
    return bool(
        getattr(
            settings,
            "supervisor_trusted_autonomy_enabled",
            False,
        )
    )


def ensure_autonomy_mode_allowed(
    settings: Any,
    autonomy_mode: str,
) -> None:
    if (
        autonomy_mode == "trusted"
        and not trusted_autonomy_enabled(settings)
    ):
        raise TrustedAutonomyDisabledError(
            TRUSTED_AUTONOMY_DISABLED_DETAIL
        )
