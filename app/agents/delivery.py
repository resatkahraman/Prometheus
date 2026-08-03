from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class DeliveryGuardResult:
    accepted: bool
    reason: str


_CODE_WRITERS = {
    "worker",
    "frontend",
    "backend",
    "database",
    "integration",
}


def _tool_succeeded(step: Any, tool: str) -> bool:
    if getattr(step, "tool", None) != tool:
        return False

    result = getattr(step, "tool_result", None)
    if not isinstance(result, dict):
        return False

    if tool == "workspace_write":
        return bool(result.get("changed"))

    if tool == "safe_terminal":
        return bool(result.get("success"))

    return False


def inspect_delivery_status(
    *,
    agent_id: str,
    answer: str,
    trace: list[Any] | None,
) -> DeliveryGuardResult:
    if agent_id not in _CODE_WRITERS or not trace:
        return DeliveryGuardResult(True, "Teslimat koruması gerekli değil.")

    write_indexes = [
        index
        for index, step in enumerate(trace)
        if _tool_succeeded(step, "workspace_write")
    ]
    if not write_indexes:
        return DeliveryGuardResult(True, "Dosya değişikliği yok.")

    last_write = max(write_indexes)
    successful_test_after_write = any(
        index > last_write and _tool_succeeded(step, "safe_terminal")
        for index, step in enumerate(trace)
    )

    has_status = re.search(
        r"\b(doğrulama durumu|test durumu|verification status)\s*:",
        answer,
        flags=re.IGNORECASE,
    )
    if not has_status:
        return DeliveryGuardResult(
            False,
            "Dosya değiştirildi; final cevap 'Doğrulama Durumu:' alanı "
            "içermelidir.",
        )

    claims_verified = re.search(
        r"\b(test edildi|doğrulandı|hatasız|çalışıyor|build başarılı|"
        r"testler geçti|verified|tests passed)\b",
        answer,
        flags=re.IGNORECASE,
    )
    admits_unverified = re.search(
        r"\b(test edilmedi|doğrulanmadı|çalıştırılamadı|"
        r"build çalıştırılmadı|not tested|not verified)\b",
        answer,
        flags=re.IGNORECASE,
    )

    if claims_verified and not successful_test_after_write and not admits_unverified:
        return DeliveryGuardResult(
            False,
            "Final cevap doğrulama iddiasında bulunuyor fakat dosya "
            "değişikliğinden sonra başarılı test/build kanıtı yok.",
        )

    if successful_test_after_write:
        if not re.search(
            r"\b(exit code|başarılı|passed|success)\b",
            answer,
            flags=re.IGNORECASE,
        ):
            return DeliveryGuardResult(
                False,
                "Test çalıştı fakat final cevap gerçek sonucu belirtmiyor.",
            )
    elif not admits_unverified:
        return DeliveryGuardResult(
            False,
            "Dosya değiştirildi fakat test yapılmadı; final cevap bunu "
            "açıkça belirtmelidir.",
        )

    return DeliveryGuardResult(True, "Teslimat doğrulama durumu açık.")
