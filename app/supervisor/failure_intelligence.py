from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


@dataclass(frozen=True)
class FailureDiagnosis:
    signature: str
    kind: str
    summary: str
    retry_tool: str | None = None
    retry_arguments: dict[str, Any] | None = None
    strategy_key: str | None = None


def _combined(result: dict[str, Any]) -> str:
    return "\n".join(
        str(result.get(key, ""))
        for key in ("stdout", "stderr", "error", "reason")
    ).replace("\r\n", "\n")


def _stable_excerpt(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"[A-Za-z]:\\[^\s]+", "<PATH>", line)
        line = re.sub(r"/[^\s]+", "<PATH>", line)
        line = re.sub(
            r"\b\d+(?:\.\d+)?\s*(?:ms|s)\b",
            "<TIME>",
            line,
            flags=re.IGNORECASE,
        )
        line = re.sub(
            r":\d+:\d+\)?$",
            ":<LINE>)",
            line,
        )
        lines.append(line[:500])
        if len(lines) >= 12:
            break
    return "\n".join(lines)


def classify_verification_failure(
    *,
    result: dict[str, Any],
    verification: str,
) -> FailureDiagnosis:
    output = _combined(result)
    lowered = output.casefold()
    exit_code = result.get("exit_code")
    command = result.get("command") or verification
    preset = str(result.get("preset", "")).casefold()
    missing = str(result.get("missing_command", "")).casefold()
    runtime_revision = str(result.get("runtime_revision", "legacy"))

    kind = "verification_failed"
    summary = f"Doğrulama exit code {exit_code} ile başarısız oldu."
    retry_tool = None
    retry_arguments = None
    strategy_key = None

    command_text = " ".join(command) if isinstance(command, list) else str(command)
    command_lower = command_text.casefold()
    is_pytest = "pytest" in verification.casefold() or "pytest" in command_lower
    is_npm = (
        verification.casefold().startswith("npm ")
        or "npm" in command_lower
        or preset.startswith("npm_")
    )
    is_node_test = (
        "node --test" in lowered
        or "node --test" in command_lower
        or verification.casefold().startswith("node --test")
    )

    if result.get("failure_kind") == "missing_command" or missing:
        if missing in {"npm", "node", "npm.cmd", "node.exe"}:
            kind = "missing_node_toolchain"
            summary = (
                "Node.js/npm bu işlem ortamında bulunamadı. Kaynak dosyalarını "
                "değiştirmek yerine Node.js LTS araç zinciri bir kez kurulmalı."
            )
            retry_tool = "safe_terminal"
            retry_arguments = {"preset": "install_node_lts", "extra_args": []}
            strategy_key = "install_node_lts"
        elif missing == "winget":
            kind = "toolchain_installer_unavailable"
            summary = (
                "Node.js/npm bulunamadı ve Windows Paket Yöneticisi (winget) "
                "de erişilebilir değil. Otomatik kurulum başlatılamadı."
            )
        else:
            kind = "missing_command"
            summary = f"Gerekli komut bulunamadı: {missing or command_text}"
    elif "import file mismatch" in lowered and is_pytest:
        kind = "pytest_import_mismatch"
        summary = (
            "Pytest aynı adlı test modüllerini klasik import modunda "
            "çakıştırdı. Kod dosyalarını yeniden yazmak yerine importlib "
            "toplama modu denenmeli."
        )
        retry_tool = "safe_terminal"
        retry_arguments = {"preset": "pytest", "extra_args": ["--import-mode=importlib"]}
        strategy_key = "pytest_importlib"
    elif preset == "npm_install" and (
        "'node' is not recognized" in lowered
        or "node: command not found" in lowered
        or "node is not recognized" in lowered
    ):
        kind = "npm_child_node_path_missing"
        summary = (
            "npm başlatıldı ancak bağımlılık kurulumunun alt süreçleri node "
            "komutunu PATH içinde göremedi. Prometheus terminal ortamını yeniden "
            "kurarak npm kurulumunu yalnızca bir kez tekrar denemeli."
        )
        retry_tool = "safe_terminal"
        retry_arguments = {"preset": "npm_install", "extra_args": []}
        strategy_key = "npm_install_repaired_path"
    elif is_npm and (
        "'vitest' is not recognized" in lowered
        or "vitest: command not found" in lowered
        or "sh: vitest: not found" in lowered
        or ("node_modules" in lowered and "not found" in lowered)
    ):
        kind = "npm_dependencies_not_installed"
        summary = (
            "npm çalışıyor ancak package.json bağımlılıkları yerel "
            "node_modules klasörüne kurulmamış. Bir kez npm install/ci "
            "çalıştırılmalı."
        )
        retry_tool = "safe_terminal"
        retry_arguments = {"preset": "npm_install", "extra_args": []}
        strategy_key = "npm_install"
    elif is_npm and (
        "referenceerror: describe is not defined" in lowered
        or "referenceerror: test is not defined" in lowered
        or "referenceerror: expect is not defined" in lowered
        or "referenceerror: it is not defined" in lowered
    ):
        if is_node_test:
            kind = "node_test_global_api_missing"
            summary = (
                "Node test dosyası global describe/test/expect API'lerini "
                "kullanıyor. Test dosyası node:test ve node:assert/strict "
                "API'lerini açıkça import etmelidir."
            )
        else:
            kind = "vitest_global_api_missing"
            summary = (
                "Vitest test dosyaları global describe/test/expect API'lerini "
                "kullanıyor. Kaynak dosyaları değiştirmek yerine test komutu "
                "--globals ile bir kez yeniden çalıştırılmalı."
            )
            retry_tool = "safe_terminal"
            retry_arguments = {
                "preset": "npm_test",
                "extra_args": ["--run", "--globals"],
            }
            strategy_key = "vitest_globals"
    elif is_npm and (
        "failed to load" in lowered
        or "cannot find package" in lowered
        or "cannot find module" in lowered
        or "err_module_not_found" in lowered
    ):
        package = None
        patterns = (
            r"failed to load\s+([^\s\r\n]+)",
            r"cannot find package\s+['\"]([^'\"]+)['\"]",
            r"cannot find module\s+['\"]([^'\"]+)['\"]",
        )
        for pattern in patterns:
            match = re.search(pattern, output, flags=re.IGNORECASE)
            if match:
                package = match.group(1).strip().rstrip(".,:;")
                break
        if package and package.startswith("@"):
            parts = package.split("/")
            package = "/".join(parts[:2]) if len(parts) >= 2 else None
        elif package:
            package = package.split("/", 1)[0]

        safe_package = bool(
            package
            and re.fullmatch(
                r"(?:@[a-z0-9._-]+/[a-z0-9._-]+|[a-z0-9][a-z0-9._-]*)",
                package,
                flags=re.IGNORECASE,
            )
        )
        kind = "missing_frontend_test_package"
        summary = (
            f"Frontend test paketi eksik: {package}. "
            "Bileşen/test içeriğini rastgele değiştirmek yerine eksik "
            "geliştirme bağımlılığı açık onayla kurulmalı."
            if safe_package
            else "Frontend testi bir paketi yükleyemedi; paket adı güvenli "
            "biçimde çıkarılamadı."
        )
        if safe_package:
            retry_tool = "safe_terminal"
            retry_arguments = {
                "preset": "npm_install_dev",
                "extra_args": [package],
            }
            strategy_key = f"npm_install_dev:{package}"
    elif (
        "modulenotfounderror" in lowered
        or "cannot find module" in lowered
        or "cannot find package" in lowered
        or "err_module_not_found" in lowered
    ):
        kind = "missing_module"
        summary = (
            "Doğrulama belirli bir modülü veya paketi bulamadı. Agent gerçek "
            "hata çıktısına göre test/kaynak dosyasını ya da izinli manifesti "
            "düzeltmeli."
        )
    elif preset == "install_node_lts":
        kind = "node_toolchain_install_failed"
        summary = "Node.js LTS araç zinciri kurulumu tamamlanamadı."
    elif preset == "npm_install":
        kind = "npm_install_failed"
        summary = "npm bağımlılık kurulumu tamamlanamadı."
    elif result.get("failure_kind") in {
        "missing_package_manifest",
        "invalid_package_manifest",
        "missing_npm_script",
    }:
        kind = str(result.get("failure_kind"))
        summary = str(result.get("message") or "Frontend manifesti eksik veya geçersiz.")
    elif "no tests ran" in lowered or "no test files found" in lowered:
        kind = "test_discovery"
        summary = "Test çalıştırıcısı doğrulanacak test dosyası bulamadı."
    elif "assertionerror" in lowered or ("failed" in lowered and "passed" in lowered):
        kind = "assertion_failure"
        summary = "Testler toplandı ancak en az bir davranış doğrulaması başarısız oldu."
    elif "syntaxerror" in lowered or "syntax error" in lowered:
        kind = "syntax_error"
        summary = "Üretilen kaynak veya test dosyasında sözdizimi hatası var."
    elif "timed out" in lowered or result.get("timed_out") is True:
        kind = "verification_timeout"
        summary = "Doğrulama komutu zaman aşımına uğradı."

    payload = {
        "kind": kind,
        "exit_code": exit_code,
        "command": command,
        "preset": preset,
        "missing_command": missing,
        "runtime_revision": runtime_revision,
        "excerpt": _stable_excerpt(output),
    }
    signature = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()

    return FailureDiagnosis(
        signature=signature,
        kind=kind,
        summary=summary,
        retry_tool=retry_tool,
        retry_arguments=retry_arguments,
        strategy_key=strategy_key,
    )
