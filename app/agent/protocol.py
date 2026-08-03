import ast
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


class AgentProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class AgentAction:
    action: str
    reason: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    answer: str | None = None


_CODE_FENCE = re.compile(
    r"^\s*```(?:json)?\s*(.*?)\s*```\s*$",
    flags=re.DOTALL | re.IGNORECASE,
)


def parse_agent_action(raw: str) -> AgentAction:
    if not isinstance(raw, str) or not raw.strip():
        raise AgentProtocolError("Model boş çıktı döndürdü.")

    candidate = raw.strip()
    fence_match = _CODE_FENCE.match(candidate)
    if fence_match:
        candidate = fence_match.group(1).strip()

    first = candidate.find("{")
    last = candidate.rfind("}")
    if first == -1 or last == -1 or last < first:
        raise AgentProtocolError("Çıktıda JSON nesnesi bulunamadı.")

    try:
        data = json.loads(candidate[first : last + 1])
    except json.JSONDecodeError as exc:
        raise AgentProtocolError(f"Geçersiz JSON: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise AgentProtocolError("Agent çıktısı JSON nesnesi olmalıdır.")

    action = data.get("action")
    reason = data.get("reason")

    if isinstance(action, str) and action.casefold() in {
        "completed",
        "complete",
        "done",
        "finished",
    }:
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            answer = (
                reason
                if isinstance(reason, str) and reason.strip()
                else "Görev tamamlandı."
            )
        return AgentAction(
            action="final",
            reason=reason if isinstance(reason, str) else None,
            answer=answer.strip(),
        )

    if action == "need_context":
        paths = data.get("paths", [])
        symbols = data.get("symbols", [])
        if not isinstance(paths, list) or not all(
            isinstance(item, str) and item.strip()
            for item in paths
        ):
            raise AgentProtocolError(
                "need_context 'paths' alanı metin listesidir."
            )
        if not isinstance(symbols, list) or not all(
            isinstance(item, str) and item.strip()
            for item in symbols
        ):
            raise AgentProtocolError(
                "need_context 'symbols' alanı metin listesidir."
            )
        if not paths and not symbols:
            raise AgentProtocolError(
                "need_context en az bir path veya symbol istemelidir."
            )
        return AgentAction(
            action="need_context",
            reason=reason if isinstance(reason, str) else None,
            arguments={
                "paths": [item.strip() for item in paths[:12]],
                "symbols": [item.strip() for item in symbols[:12]],
            },
        )

    # Providers sometimes emit {"action":"workspace_write", ...}
    # instead of the canonical tool envelope. Normalize this harmless
    # shorthand locally rather than spending another model call.
    if isinstance(action, str) and action not in {"tool", "final"}:
        shorthand_tool = action.strip()
        arguments = data.get("arguments")
        if arguments is None:
            arguments = {
                key: value
                for key, value in data.items()
                if key not in {"action", "reason", "tool", "answer"}
            }
        if isinstance(arguments, dict) and shorthand_tool:
            return AgentAction(
                action="tool",
                reason=reason if isinstance(reason, str) else None,
                tool=shorthand_tool,
                arguments=arguments,
            )

    if action == "tool":
        tool = data.get("tool")
        arguments = data.get("arguments", {})
        if not isinstance(tool, str) or not tool.strip():
            raise AgentProtocolError("Tool eyleminde 'tool' adı zorunludur.")
        if not isinstance(arguments, dict):
            raise AgentProtocolError("'arguments' JSON nesnesi olmalıdır.")
        return AgentAction(
            action="tool",
            reason=reason if isinstance(reason, str) else None,
            tool=tool.strip(),
            arguments=arguments,
        )

    if action == "final":
        answer = data.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise AgentProtocolError("Final eyleminde dolu 'answer' alanı zorunludur.")
        return AgentAction(
            action="final",
            reason=reason if isinstance(reason, str) else None,
            answer=answer.strip(),
        )

    raise AgentProtocolError(
        "'action' yalnızca 'tool', 'need_context' veya 'final' olabilir."
    )


_FILE_OPEN = re.compile(
    r'<<<ADAM_FILE(?:\s+path="([^"]+)")?\s*>>>\s*\n?',
    flags=re.IGNORECASE,
)
_FILE_CLOSE = '<<<END_ADAM_FILE>>>'
_PATCH_OPEN = re.compile(
    r'<<<ADAM_PATCH\s+path="([^"]+)"\s+base_sha256="([a-fA-F0-9]{64})"\s*>>>\s*\n?',
    flags=re.IGNORECASE,
)
_PATCH_SEARCH = "<<<SEARCH>>>"
_PATCH_REPLACE = "<<<REPLACE>>>"
_PATCH_CLOSE = "<<<END_ADAM_PATCH>>>"
_FENCED_FILE = re.compile(
    r'^\s*```(?:[a-zA-Z0-9_+.-]+)?\s*\n([\s\S]*?)\n```\s*$',
)


def _unwrap_file_fence(content: str) -> str:
    match = _FENCED_FILE.match(content.strip())
    return match.group(1) if match is not None else content


def _plain_source_is_plausible(candidate: str, expected_path: str) -> bool:
    """Conservatively recognize a complete, unwrapped source response.

    This path is only enabled for a local provider response that explicitly
    finished with ``stop``. The caller still applies source-evidence checks,
    workspace approval and the task's deterministic verification command.
    """
    suffix = expected_path.rsplit(".", 1)[-1].casefold()
    stripped = candidate.strip()
    if not stripped or "<<<ADAM_FILE" in stripped.upper():
        return False

    if suffix == "py":
        try:
            return bool(ast.parse(stripped).body)
        except SyntaxError:
            return False

    if suffix == "json":
        try:
            json.loads(stripped)
            return True
        except (TypeError, ValueError):
            return False

    if suffix in {"js", "jsx", "mjs", "ts", "tsx"}:
        source_markers = (
            "export ",
            "import ",
            "function ",
            "const ",
            "let ",
            "var ",
            "class ",
            "=>",
        )
        return any(marker in stripped for marker in source_markers)

    if suffix == "html":
        return stripped.startswith("<") and stripped.endswith(">")
    if suffix == "css":
        return "{" in stripped and "}" in stripped
    if suffix == "sql":
        return bool(
            re.match(
                r"^(select|insert|update|delete|create|alter|drop|with)\b",
                stripped,
                flags=re.IGNORECASE,
            )
        )
    if suffix == "md":
        return True
    return False


def parse_single_file_action(
    raw: str,
    expected_path: str,
    *,
    allow_plain_complete: bool = False,
) -> AgentAction:
    """Parse one complete source file without embedding it in JSON.

    Canonical agent JSON remains accepted for backwards compatibility, but
    the preferred format is an explicit file envelope. The closing marker is
    mandatory so a provider token-limit truncation can never be mistaken for
    a complete workspace write.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise AgentProtocolError("Model boş dosya çıktısı döndürdü.")
    if not isinstance(expected_path, str) or not expected_path.strip():
        raise AgentProtocolError("Beklenen kesin dosya yolu yok.")

    expected = expected_path.replace('\\', '/').strip()

    try:
        canonical = parse_agent_action(raw)
    except AgentProtocolError:
        canonical = None

    if canonical is not None:
        if canonical.action == 'final':
            return canonical
        if canonical.action == 'need_context':
            return canonical
        if canonical.tool != 'workspace_write' or not isinstance(canonical.arguments, dict):
            raise AgentProtocolError(
                "single_file çağrısı yalnızca workspace_write üretebilir."
            )
        actual = str(canonical.arguments.get('path', '')).replace('\\', '/').strip()
        content = canonical.arguments.get('content')
        if actual != expected:
            raise AgentProtocolError(
                f"Model beklenen dosya yerine '{actual}' yolunu seçti."
            )
        if not isinstance(content, str) or not content.strip():
            raise AgentProtocolError("workspace_write içeriği boş.")
        return AgentAction(
            action="tool",
            reason=canonical.reason,
            tool="workspace_write",
            arguments={
                **canonical.arguments,
                "content": _unwrap_file_fence(content).rstrip() + "\n",
            },
        )

    candidate = raw.strip()
    open_match = _FILE_OPEN.search(candidate)
    if open_match is not None:
        close_at = candidate.find(_FILE_CLOSE, open_match.end())
        if close_at < 0:
            raise AgentProtocolError(
                "Dosya çıktısı token sınırında kesildi; kapanış işareti yok."
            )
        declared = (open_match.group(1) or expected).replace('\\', '/').strip()
        if declared != expected:
            raise AgentProtocolError(
                f"Model beklenen dosya yerine '{declared}' yolunu seçti."
            )
        trailing = candidate[close_at + len(_FILE_CLOSE):].strip()
        if (
            trailing
            and (
                _FILE_OPEN.search(trailing) is not None
                or _FILE_CLOSE.casefold() in trailing.casefold()
            )
        ):
            raise AgentProtocolError(
                "Tek dosya cevabında birden fazla dosya zarfı var."
            )
        content = _unwrap_file_fence(
            candidate[open_match.end():close_at]
        )
        if not content.strip():
            raise AgentProtocolError("Model boş dosya içeriği üretti.")
        return AgentAction(
            action='tool',
            reason=f'{expected} kesin dosyasını oluştur veya güncelle.',
            tool='workspace_write',
            arguments={
                'path': expected,
                'content': content.rstrip() + '\n',
            },
        )

    fence = _FENCED_FILE.match(candidate)
    if fence is not None:
        content = fence.group(1)
        if not content.strip():
            raise AgentProtocolError("Model boş kod bloğu üretti.")
        return AgentAction(
            action='tool',
            reason=f'{expected} kesin dosyasını oluştur veya güncelle.',
            tool='workspace_write',
            arguments={
                'path': expected,
                'content': content.rstrip() + '\n',
            },
        )

    if (
        allow_plain_complete
        and _plain_source_is_plausible(candidate, expected)
    ):
        return AgentAction(
            action='tool',
            reason=(
                f'{expected} yerel model tarafından eksiksiz kaynak olarak '
                'üretildi; deterministik doğrulama kapısına gönder.'
            ),
            tool='workspace_write',
            arguments={
                'path': expected,
                'content': candidate.rstrip() + '\n',
            },
        )

    if candidate.startswith('{'):
        raise AgentProtocolError(
            "JSON dosya cevabı eksik veya kesilmiş; ham dosya protokolü kullanılmalı."
        )
    raise AgentProtocolError(
        "Tek dosya cevabı ADAM_FILE zarfında ve eksiksiz olmalıdır."
    )


def parse_single_patch_action(
    raw: str,
    expected_path: str,
    *,
    base_content: str,
    expected_sha256: str,
) -> AgentAction:
    """Apply one exact, hash-bound SEARCH/REPLACE block locally."""

    if not isinstance(raw, str) or not raw.strip():
        raise AgentProtocolError("Model boş yama çıktısı döndürdü.")
    expected = expected_path.replace("\\", "/").strip()
    actual_base_sha256 = hashlib.sha256(
        base_content.encode("utf-8")
    ).hexdigest()
    if actual_base_sha256 != expected_sha256:
        raise AgentProtocolError(
            "Yama taban dosyası çağrı hazırlanırken değişti; yeniden okunmalı."
        )

    try:
        canonical = parse_agent_action(raw)
    except AgentProtocolError:
        canonical = None
    if canonical is not None and canonical.action in {"final", "need_context"}:
        return canonical
    if canonical is not None:
        raise AgentProtocolError(
            "single_patch çağrısı yalnızca ADAM_PATCH veya final üretebilir."
        )

    candidate = raw.strip()
    opened = _PATCH_OPEN.search(candidate)
    if opened is None:
        raise AgentProtocolError("Yama cevabında ADAM_PATCH başlangıcı yok.")
    declared_path = opened.group(1).replace("\\", "/").strip()
    declared_sha256 = opened.group(2).casefold()
    if declared_path != expected:
        raise AgentProtocolError(
            f"Model beklenen dosya yerine '{declared_path}' yolunu seçti."
        )
    if declared_sha256 != expected_sha256:
        raise AgentProtocolError(
            "Model yaması beklenen dosya sürümüne bağlı değil."
        )

    search_at = candidate.find(_PATCH_SEARCH, opened.end())
    replace_at = candidate.find(
        _PATCH_REPLACE,
        search_at + len(_PATCH_SEARCH),
    )
    close_at = candidate.find(
        _PATCH_CLOSE,
        replace_at + len(_PATCH_REPLACE),
    )
    if min(search_at, replace_at, close_at) < 0:
        raise AgentProtocolError(
            "Yama kesildi; SEARCH, REPLACE veya kapanış işareti eksik."
        )
    trailing = candidate[close_at + len(_PATCH_CLOSE):].strip()
    if trailing or _PATCH_OPEN.search(candidate, opened.end()) is not None:
        raise AgentProtocolError("Tek yama cevabında fazladan içerik veya yama var.")

    search = candidate[
        search_at + len(_PATCH_SEARCH):replace_at
    ]
    replacement = candidate[
        replace_at + len(_PATCH_REPLACE):close_at
    ]
    if search.startswith("\n"):
        search = search[1:]
    if search.endswith("\n"):
        search = search[:-1]
    if replacement.startswith("\n"):
        replacement = replacement[1:]
    if replacement.endswith("\n"):
        replacement = replacement[:-1]
    if not search:
        raise AgentProtocolError("SEARCH bloğu boş olamaz.")
    occurrences = base_content.count(search)
    if occurrences != 1:
        raise AgentProtocolError(
            "SEARCH bloğu taban dosyada tam bir kez eşleşmelidir; "
            f"eşleşme sayısı: {occurrences}."
        )
    updated = base_content.replace(search, replacement, 1)
    if not updated.strip():
        raise AgentProtocolError("Yama hedef dosyanın tamamını boşaltamaz.")
    return AgentAction(
        action="tool",
        reason=f"{expected} için hash-bağlı güvenli yama uygula.",
        tool="workspace_write",
        arguments={"path": expected, "content": updated},
    )
