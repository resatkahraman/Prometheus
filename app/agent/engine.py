import asyncio
import hashlib
import json
from pathlib import Path
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from app.agent.intent import (
    ToolSuggestion,
    last_user_text,
    suggest_deterministic_tool,
)
from app.agent.protocol import (
    AgentProtocolError,
    parse_agent_action,
    parse_single_file_action,
    parse_single_patch_action,
)
from app.agents.models import AgentProfile
from app.agents.quality import inspect_agent_answer
from app.agents.registry import AgentRegistry, build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import (
    AgentRequest,
    AgentResponse,
    AgentStep,
    ApprovalInfo,
    ChatMessage,
    OrchestrateRequest,
    RouteScore,
)
from app.memory.project import ProjectMemoryStore
from app.memory.project_dna import ProjectDNAError, ProjectDNAManager
from app.orchestration.orchestrator import Orchestrator
from app.tools.base import ToolApprovalRequired, ToolError
from app.tools.fingerprint import tool_fingerprint
from app.tools.registry import ToolRegistry


@dataclass(frozen=True)
class AgentApprovalApplication:
    session_id: str
    approval_id: str
    tool_name: str
    success: bool
    result: Any


@dataclass
class AgentSession:
    id: str
    request: AgentRequest
    profile: AgentProfile
    messages: list[ChatMessage]
    trace: list[AgentStep]
    tools_used: list[str]
    model_calls: int
    last_scores: list[RouteScore]
    final_route: str | None
    final_provider: str | None
    final_model: str | None
    max_steps: int
    max_model_calls: int
    next_step: int
    pending_approval_id: str | None
    created_monotonic: float
    quality_retries: int = 0
    excluded_routes: list[str] = field(default_factory=list)
    project_context: dict[str, Any] | None = None
    protocol_retries: int = 0
    local_protocol_repairs: int = 0
    base_message_count: int = 0
    context_expansions: int = 0
    evidence_retries: int = 0


def _generated_source_contract_issue(
    *,
    path: str,
    content: str,
    instruction: str,
) -> str | None:
    normalized_path = path.replace("\\", "/").casefold()
    is_javascript_test = (
        any(
            part in normalized_path
            for part in ("/test/", "/tests/", "/__tests__/")
        )
        or re.search(
            r"(?:^|[._-])(?:test|spec)(?:[._-]|$)",
            Path(normalized_path).name,
        )
        is not None
    ) and Path(normalized_path).suffix in {
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
    }
    if not is_javascript_test:
        return None

    lowered_instruction = instruction.casefold()
    lowered_content = content.casefold()
    missing: list[str] = []
    for required in ("node:test", "node:assert/strict"):
        if required in lowered_instruction and required not in lowered_content:
            missing.append(required)
    if missing:
        return (
            "Test sözleşmesinin zorunlu importları eksik: "
            + ", ".join(missing)
            + ". Jest/Vitest globalleri yerine bu yerleşik Node modüllerini "
            "açıkça import et."
        )
    return None


class AgentEngine:
    def __init__(
        self,
        *,
        settings: Settings,
        orchestrator: Orchestrator,
        tools: ToolRegistry,
        agents: AgentRegistry | None = None,
        project_dna: ProjectDNAManager | None = None,
    ) -> None:
        self.settings = settings
        self.orchestrator = orchestrator
        self.tools = tools
        self.agents = agents or build_default_agent_registry(tools.names())
        self.project_dna = (
            project_dna
            if project_dna is not None
            else ProjectDNAManager(
                workspace_root=settings.workspace_root,
                enabled=settings.project_dna_enabled,
                max_file_bytes=settings.project_dna_max_file_bytes,
                max_context_chars=settings.project_dna_context_max_chars,
                max_search_results=settings.workspace_max_search_results,
            )
        )
        self._sessions: dict[str, AgentSession] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._approval_flow_locks: dict[
            tuple[str, str],
            asyncio.Lock,
        ] = {}
        self._approval_replays: dict[
            tuple[str, str, str],
            tuple[float, AgentResponse],
        ] = {}
        self._approval_application_replays: dict[
            tuple[str, str],
            tuple[float, AgentApprovalApplication],
        ] = {}
        memory_path = settings.project_memory_database_path
        if not memory_path.is_absolute():
            memory_path = settings.workspace_root / memory_path
        self.project_memory = ProjectMemoryStore(
            Path(memory_path),
            enabled=settings.project_memory_enabled,
        )

    @staticmethod
    def _has_eligible_alternative(
        session: AgentSession,
        selected_route: str,
    ) -> bool:
        excluded = set(session.excluded_routes)
        return any(
            score.eligible
            and score.route_key != selected_route
            and score.route_key not in excluded
            for score in session.last_scores
        )

    def _system_prompt(
        self,
        profile: AgentProfile,
        request: AgentRequest | None = None,
    ) -> str:
        if request is not None and request.response_protocol == "single_patch":
            expected = (request.single_file_path or "").strip()
            base_sha256 = request.single_file_base_sha256 or ""
            mission = " ".join(profile.mission)
            instructions = " ".join(profile.instructions)
            return f"""ZORUNLU HASH-BAĞLI TEK YAMA ÇIKTISI:
<<<ADAM_PATCH path="{expected}" base_sha256="{base_sha256}">>>
<<<SEARCH>>>
TABAN DOSYADAN HARFİYEN VE TEK KEZ GEÇEN KISA BLOK
<<<REPLACE>>>
YENİ BLOK
<<<END_ADAM_PATCH>>>

Kesin hedef: {expected}
Kesin taban sha256: {base_sha256}

Kurallar:
1. Yalnızca bir SEARCH/REPLACE bloğu üret; JSON, Markdown ve açıklama üretme.
2. SEARCH, verilen taban dosyada harfiyen ve tam bir kez bulunmalı.
3. Dosyanın tamamını tekrar üretme; değişmesi gereken en küçük güvenli bloğu seç.
4. Yol veya hash değerini değiştirme; kapanış işaretini mutlaka üret.
5. Başka dosya ya da terminal işlemi isteme.
6. Gerekli bağlam yoksa yalnızca need_context JSON'u döndür.
7. Hedef zaten doğruysa final JSON'u ile kısa neden ver.

Rol: Prometheus içindeki {profile.name} ({profile.description}).
Misyon: {mission}
Ek rol kuralı: {instructions or "Yok."}
"""
        if request is not None and request.response_protocol == "single_file":
            expected = (request.single_file_path or "").strip()
            mission = " ".join(profile.mission)
            instructions = " ".join(profile.instructions)
            return f"""ZORUNLU TEK DOSYA ÇIKTISI — İLK VE SON KARAKTERLER BU ZARFA AİT OLMALI:
<<<ADAM_FILE path="{expected}">>>
DOSYANIN TAM VE HAM İÇERİĞİ
<<<END_ADAM_FILE>>>

Kesin hedef: {expected}

Kurallar:
1. JSON üretme. Markdown açıklaması veya kod çiti üretme.
2. Başlangıç ve kapanış işaretlerini harfiyen kullan.
3. Dosyayı kesmeden, derlenebilir ve eksiksiz üret.
4. Yalnızca {expected} içeriğini üret; başka dosya veya terminal işlemi isteme.
5. Bu çağrı başarısız doğrulama kanıtından sonraki onarım adımıdır. "Değişiklik
   gerekmiyor" veya final JSON'u döndürme; hedef dosyanın düzeltilmiş tamamını üret.
6. Gereksiz yorum, uzun stil nesneleri ve tekrarlarla çıktıyı şişirme.
7. Gerekli bir dosya veya sembol bağlamda yoksa tahmin etme; yalnızca şu
   JSON ile bağlam iste:
{{"action":"need_context","reason":"...","paths":["src/x"],"symbols":["name"]}}
8. Yerel bir modülden yalnızca kanıtlı export/sembolleri import et; olmayan
   export, sabit, fonksiyon veya sınıf adı uydurma.

Rol: Prometheus içindeki {profile.name} ({profile.description}).
Misyon: {mission}
Ek rol kuralı: {instructions or "Yok."}
"""

        definitions = json.dumps(
            self.tools.definitions(profile.allowed_tools),
            ensure_ascii=False,
            indent=2,
        )
        return f"""Sen Prometheus v0.8.0 içindeki uzman agentsın.

{profile.prompt_block()}

Ortak kurallar:
1. Yalnızca rol ve izinlerin içinde çalış.
2. Sana AUTO_PROJECT_CONTEXT verildiyse onu gerçek proje kanıtı olarak kullan.
3. Eksik bağlam varsa project_summary/workspace_list/search/read kullan.
4. Görmediğin dosyayı veya test sonucunu uydurma.
5. Yazmadan önce mevcut dosyayı oku.
6. workspace_write ve safe_terminal kullanıcı onayı gerektirir.
7. TOOL_RESULT başarısızsa başarı deme.
8. Değişiklikten sonra git_diff ve uygun testi kullan.
9. Hesapta calculator veya symbolic_math kullan.
10. Rol dışı işi yapma; gereken uzmanı belirt.
11. Final cevap ZORUNLU çıktı sözleşmesindeki her bölümü gerçekten içermeli.
12. 'Hazırlandı', 'tanımlandı' veya 'tamamlandı' deyip içeriği gizleme.
13. Dosya değiştirdiysen final cevapta 'Doğrulama Durumu:' alanı ver.
14. Test çalışmadıysa kodun çalıştığını veya doğrulandığını iddia etme.
15. Görev isteğinde exclusive_write_paths varsa bunlar bağlayıcıdır; alternatif klasöre yazma.
16. Daha önce uygulanmış işlem parmak izini tekrar üretme.
17. Dosya zaten hedef içerikle aynıysa yeni yazma isteme; doğrulama adımına geç.
18. Sadece şu JSON biçimlerinden birini döndür.

Araç:
{{"action":"tool","reason":"...","tool":"araç","arguments":{{}}}}

Eksik bağlam:
{{"action":"need_context","reason":"...","paths":["src/x"],"symbols":["name"]}}

Final:
{{"action":"final","reason":"...","answer":"Eksiksiz teslim edilen cevap"}}

Kullanılabilir araçlar:
{definitions}"""

    def _tool_message(
        self,
        tool: str,
        success: bool,
        result: Any,
    ) -> ChatMessage:
        prompt_result = self._compact_tool_result(tool, result)
        text = json.dumps(
            {
                "type": "TOOL_RESULT",
                "tool": tool,
                "success": success,
                "result": prompt_result,
            },
            ensure_ascii=False,
            default=str,
        )
        if len(text) > self.settings.agent_tool_result_max_chars:
            text = json.dumps(
                {
                    "type": "TOOL_RESULT",
                    "tool": tool,
                    "success": success,
                    "result": {
                        "prompt_truncated": True,
                        "summary": self._clip_prompt_text(
                            json.dumps(
                                prompt_result,
                                ensure_ascii=False,
                                default=str,
                            ),
                            self.settings.agent_tool_result_max_chars - 300,
                        ),
                    },
                },
                ensure_ascii=False,
            )
        return ChatMessage(
            role="user",
            content=text + "\nSonraki JSON eylemini üret.",
        )

    @staticmethod
    def _clip_prompt_text(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        if limit <= 80:
            return text[:limit]
        marker = "\n... bağlam özeti kırpıldı ...\n"
        available = limit - len(marker)
        head = max(1, int(available * 0.65))
        tail = max(1, available - head)
        return text[:head] + marker + text[-tail:]

    @staticmethod
    def _tail_prompt_text(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        marker = "... önceki terminal çıktısı kırpıldı ...\n"
        return marker + text[-max(1, limit - len(marker)) :]

    def _compact_tool_result(self, tool: str, result: Any) -> Any:
        if not isinstance(result, dict):
            rendered = json.dumps(result, ensure_ascii=False, default=str)
            if len(rendered) <= self.settings.agent_tool_content_max_chars:
                return result
            return {
                "prompt_truncated": True,
                "summary": self._clip_prompt_text(
                    rendered,
                    self.settings.agent_tool_content_max_chars,
                ),
            }

        compact = dict(result)
        content_limit = self.settings.agent_tool_content_max_chars

        if tool == "workspace_read" and isinstance(
            compact.get("content"),
            str,
        ):
            original = compact["content"]
            compact["content"] = self._clip_prompt_text(
                original,
                content_limit,
            )
            compact["prompt_truncated"] = len(original) > content_limit
        elif tool == "workspace_list" and isinstance(
            compact.get("entries"),
            list,
        ):
            entries = compact["entries"]
            compact["entries"] = entries[:60]
            compact["prompt_entries_omitted"] = max(0, len(entries) - 60)
        elif tool == "workspace_search" and isinstance(
            compact.get("results"),
            list,
        ):
            results = compact["results"]
            compact["results"] = results[:30]
            compact["prompt_results_omitted"] = max(0, len(results) - 30)
        elif tool == "safe_terminal":
            for key in ("stdout", "stderr", "output"):
                if isinstance(compact.get(key), str):
                    compact[key] = self._tail_prompt_text(
                        compact[key],
                        content_limit,
                    )
        elif tool == "git_diff":
            for key in ("diff", "stdout", "output"):
                if isinstance(compact.get(key), str):
                    compact[key] = self._clip_prompt_text(
                        compact[key],
                        content_limit,
                    )

        rendered = json.dumps(compact, ensure_ascii=False, default=str)
        if len(rendered) <= self.settings.agent_tool_result_max_chars:
            return compact
        return {
            "prompt_truncated": True,
            "summary": self._clip_prompt_text(
                rendered,
                self.settings.agent_tool_content_max_chars,
            ),
        }

    def _compact_assistant_history(self, content: str) -> str:
        marker = '<<<ADAM_FILE path="'
        if marker in content:
            start = content.find(marker) + len(marker)
            end = content.find('">>>', start)
            path = content[start:end] if end > start else "unknown"
            return json.dumps(
                {
                    "action": "tool_receipt",
                    "tool": "workspace_write",
                    "path": path,
                    "content_chars": len(content),
                    "content_sha256": hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest(),
                    "note": (
                        "Tam dosya içeriği token tasarrufu için geçmişten "
                        "çıkarıldı; gerekirse workspace_read kullan."
                    ),
                },
                ensure_ascii=False,
            )

        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return self._clip_prompt_text(
                content,
                self.settings.agent_tool_content_max_chars,
            )

        if (
            isinstance(payload, dict)
            and payload.get("action") == "tool"
            and payload.get("tool") == "workspace_write"
            and isinstance(payload.get("arguments"), dict)
            and isinstance(payload["arguments"].get("content"), str)
        ):
            compact = dict(payload)
            arguments = dict(payload["arguments"])
            file_content = arguments.pop("content")
            arguments["content_receipt"] = {
                "chars": len(file_content),
                "sha256": hashlib.sha256(
                    file_content.encode("utf-8")
                ).hexdigest(),
                "state": "held_by_approval_or_workspace",
            }
            compact["arguments"] = arguments
            return json.dumps(compact, ensure_ascii=False)

        return self._clip_prompt_text(
            content,
            self.settings.agent_tool_content_max_chars,
        )

    def _trace_memory(self, session: AgentSession) -> str | None:
        records: list[dict[str, Any]] = []
        for step in session.trace[-40:]:
            if step.action == "context":
                result = step.tool_result
                paths: list[str] = []
                if isinstance(result, dict):
                    selection = result.get("selection")
                    if isinstance(selection, dict):
                        paths = list(selection.get("selected_paths") or [])
                records.append(
                    {
                        "step": step.step,
                        "action": "context",
                        "paths": paths[:12],
                    }
                )
                continue

            record: dict[str, Any] = {
                "step": step.step,
                "action": step.action,
            }
            if step.tool:
                record["tool"] = step.tool
            if step.reason and step.action in {
                "protocol_error",
                "quality_rejected",
                "approval_required",
            }:
                record["reason"] = step.reason[:500]

            arguments = step.arguments or {}
            result = (
                step.tool_result
                if isinstance(step.tool_result, dict)
                else {}
            )
            if step.tool in {"workspace_read", "workspace_write"}:
                record["path"] = (
                    result.get("path")
                    or arguments.get("path")
                )
            if step.tool == "workspace_write":
                record["changed"] = result.get("changed")
                record["sha256"] = (
                    result.get("new_sha256")
                    or result.get("old_sha256")
                )
            elif step.tool == "workspace_read":
                record["lines"] = [
                    result.get("start_line"),
                    result.get("end_line"),
                ]
            elif step.tool == "safe_terminal":
                record["command"] = result.get("command")
                record["exit_code"] = result.get("exit_code")
                record["success"] = result.get("success")
            elif step.tool == "workspace_search":
                record["query"] = arguments.get("query")
                matches = result.get("results")
                record["matches"] = (
                    len(matches) if isinstance(matches, list) else None
                )
            elif step.tool == "workspace_list":
                entries = result.get("entries")
                record["entries"] = (
                    len(entries) if isinstance(entries, list) else None
                )
            records.append(record)

        if not records:
            return None
        rendered = json.dumps(
            {
                "type": "SESSION_MEMORY",
                "note": (
                    "Bu kayıt yalnızca uygulanmış işlemlerin kısa makbuzudur. "
                    "Tam içerik gerekirse dosyayı yeniden oku; işlemi tekrarlama."
                ),
                "records": records,
            },
            ensure_ascii=False,
            default=str,
        )
        return self._clip_prompt_text(
            rendered,
            self.settings.agent_context_memory_max_chars,
        )

    def _fit_messages(
        self,
        messages: list[ChatMessage],
        *,
        budget: int,
        assistant_compaction: bool = False,
    ) -> list[ChatMessage]:
        if budget <= 0 or not messages:
            return []

        remaining = budget
        selected: list[ChatMessage] = []
        for message in reversed(messages):
            content = (
                self._compact_assistant_history(message.content)
                if assistant_compaction and message.role == "assistant"
                else message.content
            )
            if remaining <= 0:
                break
            clipped = self._clip_prompt_text(content, remaining)
            selected.append(
                ChatMessage(role=message.role, content=clipped)
            )
            remaining -= len(clipped)
        return list(reversed(selected))

    def _compiled_messages(self, session: AgentSession) -> list[ChatMessage]:
        max_chars = min(
            self.settings.agent_context_max_chars,
            self.settings.max_input_chars,
        )
        base = session.messages[: session.base_message_count]
        live = session.messages[session.base_message_count :]
        recent = live[-self.settings.agent_context_recent_messages :]

        recent_budget = (
            min(
                self.settings.agent_tool_content_max_chars,
                max_chars // 3,
            )
            if recent
            else 0
        )
        memory_text = self._trace_memory(session)
        memory_budget = (
            min(
                self.settings.agent_context_memory_max_chars,
                max_chars // 6,
            )
            if memory_text
            else 0
        )
        context_budget = (
            min(
                self.settings.agent_project_context_max_chars,
                max_chars // 3,
            )
            if session.project_context
            else 0
        )
        base_budget = min(
            self.settings.agent_context_base_max_chars,
            max_chars - recent_budget - memory_budget - context_budget,
        )
        base_budget = max(1, base_budget)

        compiled = self._fit_messages(base, budget=base_budget)

        if session.project_context and context_budget:
            serialized = json.dumps(
                {
                    "type": "AUTO_PROJECT_CONTEXT",
                    "result": session.project_context,
                },
                ensure_ascii=False,
                default=str,
            )
            compiled.append(
                ChatMessage(
                    role="user",
                    content=(
                        self._clip_prompt_text(
                            serialized,
                            context_budget,
                        )
                        + "\nBu görev için seçilmiş bağlamı kullan."
                    ),
                )
            )

        if memory_text and memory_budget:
            compiled.append(
                ChatMessage(
                    role="user",
                    content=self._clip_prompt_text(
                        memory_text,
                        memory_budget,
                    ),
                )
            )

        compiled.extend(
            self._fit_messages(
                recent,
                budget=recent_budget,
                assistant_compaction=True,
            )
        )

        total = sum(len(item.content) for item in compiled)
        if total <= max_chars:
            return compiled
        return self._fit_messages(compiled, budget=max_chars)

    def _request(self, session: AgentSession) -> OrchestrateRequest:
        return OrchestrateRequest(
            messages=self._compiled_messages(session),
            mode=session.request.routing_mode,
            provider=session.request.provider,
            preferred_routes=(
                session.request.preferred_routes
                or session.profile.preferred_routes
            ),
            excluded_routes=session.excluded_routes or None,
            task_type_override=session.profile.task_type_override,
            system_prompt=self._system_prompt(
                session.profile,
                session.request,
            ),
            temperature=(
                0.0
                if session.request.response_protocol in {
                    "single_file",
                    "single_patch",
                }
                else session.profile.temperature
            ),
            max_output_tokens=(
                session.request.max_output_tokens
                or self.settings.agent_step_output_tokens
            ),
            include_candidates=False,
            bypass_cache=True,
            usage_scope=session.request.usage_scope,
            usage_task_id=session.request.usage_task_id,
            task_signature=session.request.task_signature,
        )

    def _cleanup(self) -> None:
        now = time.monotonic()
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if (
                now - session.created_monotonic
                > self.settings.agent_session_ttl_seconds
            )
        ]
        for session_id in expired:
            self._sessions.pop(session_id, None)
            self._session_locks.pop(session_id, None)

        replay_expired = [
            key
            for key, (created, _response) in self._approval_replays.items()
            if (
                now - created
                > self.settings.agent_approval_replay_ttl_seconds
            )
        ]
        for key in replay_expired:
            self._approval_replays.pop(key, None)

        application_expired = [
            key
            for key, (created, _application)
            in self._approval_application_replays.items()
            if (
                now - created
                > self.settings.agent_approval_replay_ttl_seconds
            )
        ]
        for key in application_expired:
            self._approval_application_replays.pop(key, None)

    def _session_lock(self, session_id: str) -> asyncio.Lock:
        lock = self._session_locks.get(session_id)
        if lock is None:
            lock = asyncio.Lock()
            self._session_locks[session_id] = lock
        return lock

    def _approval_flow_lock(
        self,
        session_id: str,
        approval_id: str,
    ) -> asyncio.Lock:
        key = (session_id, approval_id)
        lock = self._approval_flow_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._approval_flow_locks[key] = lock
        return lock

    def _approval_replay(
        self,
        *,
        action: str,
        session_id: str,
        approval_id: str,
    ) -> AgentResponse | None:
        item = self._approval_replays.get(
            (action, session_id, approval_id)
        )
        if item is None:
            return None
        return item[1].model_copy(deep=True)

    def _store_approval_replay(
        self,
        *,
        action: str,
        session_id: str,
        approval_id: str,
        response: AgentResponse,
    ) -> None:
        self._approval_replays[(action, session_id, approval_id)] = (
            time.monotonic(),
            response.model_copy(deep=True),
        )

    def approval_snapshot(self, session_id: str) -> dict[str, Any]:
        self._cleanup()
        session = self._sessions.get(session_id)
        return {
            "session_exists": session is not None,
            "pending_approval_id": (
                session.pending_approval_id if session else None
            ),
        }

    def _response(
        self,
        session: AgentSession,
        answer: str,
        status: str,
        pending: dict[str, Any] | None = None,
    ) -> AgentResponse:
        return AgentResponse(
            answer=answer,
            agent_id=session.profile.id,
            agent_name=session.profile.name,
            status=status,
            steps_used=len(session.trace),
            model_calls_used=session.model_calls,
            tools_used=list(dict.fromkeys(session.tools_used)),
            final_route=session.final_route,
            final_provider=session.final_provider,
            final_model=session.final_model,
            routing_scores=session.last_scores,
            trace=session.trace if session.request.include_trace else None,
            session_id=(
                session.id
                if status == "awaiting_approval"
                else None
            ),
            pending_approval=ApprovalInfo(**pending) if pending else None,
        )

    def _pause(
        self,
        session: AgentSession,
        step: int,
        pending,
        reason: str,
        route: str,
        provider: str,
        model: str,
        latency: int,
        raw: str | None,
        arguments: dict[str, Any],
    ) -> AgentResponse:
        data = pending.public_dict()
        session.trace.append(
            AgentStep(
                step=step,
                selected_route=route,
                provider=provider,
                model=model,
                action="approval_required",
                reason=reason,
                tool=pending.tool_name,
                arguments=arguments,
                tool_result=data,
                latency_ms=latency,
                raw_output=raw,
            )
        )
        session.pending_approval_id = pending.id
        session.next_step = step + 1
        self._sessions[session.id] = session
        return self._response(
            session,
            (
                f"{pending.tool_name} işlemi "
                f"{session.profile.short_name} agentı tarafından hazırlandı. "
                "Devam etmek için onay gerekiyor."
            ),
            "awaiting_approval",
            data,
        )

    def _authorize(
        self,
        session: AgentSession,
        suggestion: ToolSuggestion,
    ) -> None:
        self.agents.authorize(
            profile=session.profile,
            tool_name=suggestion.tool,
            arguments=suggestion.arguments,
        )

    async def _bootstrap_context(
        self,
        session: AgentSession,
    ) -> None:
        if (
            not session.profile.auto_context
            or session.request.disable_auto_context
        ):
            return
        if session.next_step > session.max_steps:
            return

        context: dict[str, Any] = {
            "summary": None,
            "tree": None,
            "files": [],
            "selection": {
                "target_paths": list(
                    dict.fromkeys(
                        [
                            *session.request.exclusive_write_paths,
                            *session.request.additional_write_paths,
                        ]
                    )
                ),
                "selected_paths": [],
            },
        }
        failures: list[str] = []

        try:
            dna_context = self.project_dna.context(".")
        except ProjectDNAError:
            failures.append("project_dna: invalid or unavailable")
        else:
            if dna_context is not None:
                context["project_dna"] = dna_context.to_prompt_payload()

        try:
            self.agents.authorize(
                profile=session.profile,
                tool_name="project_summary",
                arguments={},
            )
            context["summary"] = await self.tools.execute(
                "project_summary",
                {},
            )
            session.tools_used.append("project_summary")
        except Exception as exc:
            failures.append(f"project_summary: {exc}")

        try:
            list_arguments = {
                "path": ".",
                "depth": 3,
                "max_entries": 180,
            }
            self.agents.authorize(
                profile=session.profile,
                tool_name="workspace_list",
                arguments=list_arguments,
            )
            context["tree"] = await self.tools.execute(
                "workspace_list",
                list_arguments,
            )
            if isinstance(context["tree"], dict):
                entries = context["tree"].get("entries")
                if isinstance(entries, list) and len(entries) > 80:
                    context["tree"] = {
                        **context["tree"],
                        "entries": entries[:80],
                        "prompt_entries_omitted": len(entries) - 80,
                    }
            session.tools_used.append("workspace_list")
        except Exception as exc:
            failures.append(f"workspace_list: {exc}")

        target_paths = list(
            dict.fromkeys(
                [
                    *session.request.exclusive_write_paths,
                    *session.request.additional_write_paths,
                ]
            )
        )
        target_set = set(target_paths)
        candidate_paths: list[str] = list(target_paths)
        summary = context.get("summary")
        if isinstance(summary, dict):
            candidate_paths.extend(summary.get("manifests", []))

        tree = context.get("tree")
        if isinstance(tree, dict):
            entries = tree.get("entries", [])
            file_paths = [
                item.get("path")
                for item in entries
                if item.get("type") == "file" and item.get("path")
            ]
            priority_names = {
                "readme.md": 0,
                "pyproject.toml": 1,
                "requirements.txt": 2,
                "package.json": 3,
                "pubspec.yaml": 4,
                "cargo.toml": 5,
                "app.py": 6,
                "main.py": 7,
                "app/main.py": 8,
                "src/main.py": 9,
                "src/index.ts": 10,
                "src/index.tsx": 11,
            }

            def priority(path: str) -> tuple[int, int, str]:
                lowered = path.casefold()
                name = lowered.rsplit("/", 1)[-1]
                direct = priority_names.get(lowered)
                if direct is None:
                    direct = priority_names.get(name, 100)
                depth = lowered.count("/")
                return direct, depth, lowered

            candidate_paths.extend(sorted(file_paths, key=priority))

        unique_paths = list(dict.fromkeys(candidate_paths))
        max_files = self.settings.agent_auto_context_max_files

        for path in unique_paths[:max_files]:
            try:
                arguments = {
                    "path": path,
                    "start_line": 1,
                    "end_line": self.settings.agent_auto_context_max_lines,
                }
                self.agents.authorize(
                    profile=session.profile,
                    tool_name="workspace_read",
                    arguments=arguments,
                )
                content = await self.tools.execute(
                    "workspace_read",
                    arguments,
                )
                memory = await self.project_memory.remember_file(
                    path=str(content.get("path") or path),
                    content=str(content.get("content") or ""),
                )
                prompt_file = dict(content)
                prompt_file["memory"] = {
                    "state": memory.state,
                    "sha256": memory.sha256,
                    "size_bytes": memory.size_bytes,
                }
                if memory.state == "unchanged" and path not in target_set:
                    prompt_file.pop("content", None)
                    prompt_file["memory_outline"] = memory.outline
                    prompt_file["content_mode"] = "outline"
                else:
                    prompt_file["content_mode"] = "full"
                context["files"].append(prompt_file)
                context["selection"]["selected_paths"].append(
                    str(content.get("path") or path)
                )
                session.tools_used.append("workspace_read")
            except Exception as exc:
                failures.append(f"workspace_read({path}): {exc}")

        if failures:
            context["warnings"] = failures

        session.project_context = context

        serialized_context = json.dumps(
            context,
            ensure_ascii=False,
            default=str,
        )
        await self.project_memory.record_context(
            source="agent_bootstrap",
            task_text=(
                session.request.message
                or "\n".join(
                    item.content
                    for item in session.request.normalized_messages()
                )
            ),
            context_chars=min(
                len(serialized_context),
                self.settings.agent_project_context_max_chars,
            ),
            full_file_count=sum(
                1
                for item in context["files"]
                if item.get("content_mode") == "full"
            ),
            summarized_file_count=sum(
                1
                for item in context["files"]
                if item.get("content_mode") == "outline"
            ),
            selected_paths=context["selection"]["selected_paths"],
        )

        session.trace.append(
            AgentStep(
                step=session.next_step,
                selected_route="deterministic",
                provider="local-tool",
                model="context-bootstrap",
                action="context",
                reason=(
                    "Rol, karar vermeden önce gerçek proje bağlamını "
                    "otomatik toplar."
                ),
                tool="auto_project_context",
                arguments={
                    "max_files": max_files,
                    "max_lines": self.settings.agent_auto_context_max_lines,
                },
                tool_result=context,
                latency_ms=0,
                raw_output=None,
            )
        )

        session.next_step += 1

    async def _expand_context(
        self,
        session: AgentSession,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        requested_paths = [
            str(item).strip()
            for item in arguments.get("paths", [])
            if str(item).strip()
        ]
        symbols = [
            str(item).strip()
            for item in arguments.get("symbols", [])
            if str(item).strip()
        ]
        symbol_paths = await self.project_memory.resolve_symbols(symbols)
        paths = list(
            dict.fromkeys([*requested_paths, *symbol_paths])
        )[: self.settings.agent_context_expansion_max_files]

        files: list[dict[str, Any]] = []
        missing: list[str] = []
        for path in paths:
            arguments_for_read = {
                "path": path,
                "start_line": 1,
                "end_line": self.settings.agent_context_expansion_max_lines,
            }
            try:
                self.agents.authorize(
                    profile=session.profile,
                    tool_name="workspace_read",
                    arguments=arguments_for_read,
                )
                result = await self.tools.execute(
                    "workspace_read",
                    arguments_for_read,
                )
            except Exception as exc:
                missing.append(f"{path}: {type(exc).__name__}: {exc}")
                continue
            memory = await self.project_memory.remember_file(
                path=str(result.get("path") or path),
                content=str(result.get("content") or ""),
            )
            files.append(
                {
                    **result,
                    "memory": {
                        "sha256": memory.sha256,
                        "state": memory.state,
                    },
                    "requested_by": {
                        "paths": requested_paths,
                        "symbols": symbols,
                    },
                }
            )
            session.tools_used.append("workspace_read")

        if session.project_context is None:
            session.project_context = {
                "summary": None,
                "tree": None,
                "files": [],
                "selection": {
                    "target_paths": list(
                        session.request.exclusive_write_paths
                    ),
                    "selected_paths": [],
                },
            }
        expansions = session.project_context.setdefault(
            "adaptive_expansions",
            [],
        )
        expansions.append(
            {
                "files": files,
                "missing": missing,
                "requested_paths": requested_paths,
                "requested_symbols": symbols,
            }
        )
        session.project_context["selection"][
            "selected_paths"
        ] = list(
            dict.fromkeys(
                [
                    *session.project_context["selection"].get(
                        "selected_paths",
                        [],
                    ),
                    *[
                        str(item.get("path"))
                        for item in files
                        if item.get("path")
                    ],
                ]
            )
        )
        session.context_expansions += 1
        await self.project_memory.record_context(
            source="adaptive_expansion",
            task_text=(
                f"{session.request.usage_scope or session.id}:"
                f"{session.request.usage_task_id or ''}:"
                f"{requested_paths}:{symbols}"
            ),
            context_chars=len(
                json.dumps(files, ensure_ascii=False, default=str)
            ),
            full_file_count=len(files),
            summarized_file_count=0,
            selected_paths=[
                str(item.get("path"))
                for item in files
                if item.get("path")
            ],
        )
        return {
            "files": files,
            "missing": missing,
            "requested_paths": requested_paths,
            "requested_symbols": symbols,
        }

    @staticmethod
    def _local_math_answer(
        suggestion: ToolSuggestion,
        result: dict[str, Any],
    ) -> str:
        operation = suggestion.arguments.get("operation")
        value = result.get("result")
        expression = result.get("expression")

        if operation == "differentiate":
            return f"Türev: {value}"
        if operation == "integrate":
            return f"Belirsiz integral: {value} + C"
        if operation == "solve":
            return f"Çözümler: {value}"
        if operation == "simplify":
            return f"Sadeleştirilmiş ifade: {value}"
        if operation == "evaluate":
            return f"Sonuç: {value}"

        return f"İfade: {expression}\nSonuç: {value}"

    async def _run_deterministic_suggestion(
        self,
        session: AgentSession,
        suggestion: ToolSuggestion,
    ) -> AgentResponse | None:
        if session.next_step > session.max_steps:
            return None

        session.tools_used.append(suggestion.tool)
        try:
            self._authorize(session, suggestion)
            result = await self.tools.execute(
                suggestion.tool,
                suggestion.arguments,
            )
            success = True
        except ToolApprovalRequired as exc:
            return self._pause(
                session,
                session.next_step,
                exc.pending,
                suggestion.reason,
                "deterministic",
                "local-tool",
                "intent-resolver",
                0,
                None,
                suggestion.arguments,
            )
        except (ToolError, ValueError, TypeError) as exc:
            result = {"error": str(exc)}
            success = False

        session.trace.append(
            AgentStep(
                step=session.next_step,
                selected_route="deterministic",
                provider="local-tool",
                model="intent-resolver",
                action="tool",
                reason=suggestion.reason,
                tool=suggestion.tool,
                arguments=suggestion.arguments,
                tool_result=result,
                latency_ms=0,
                raw_output=None,
            )
        )
        session.next_step += 1

        if (
            success
            and session.profile.id == "calculation"
            and suggestion.tool == "symbolic_math"
        ):
            session.final_route = "deterministic"
            session.final_provider = "local-tool"
            session.final_model = "sympy"
            return self._response(
                session,
                self._local_math_answer(suggestion, result),
                "completed",
            )

        session.messages.append(
            self._tool_message(
                suggestion.tool,
                success,
                result,
            )
        )
        return None

    async def run(self, request: AgentRequest) -> AgentResponse:
        self._cleanup()
        profile = self.agents.get(request.agent_id)
        if request.exclusive_write_paths and not profile.read_only:
            profile = profile.model_copy(
                update={
                    "write_paths": list(
                        dict.fromkeys(
                            request.exclusive_write_paths
                        )
                    )
                }
            )
        elif request.additional_write_paths and not profile.read_only:
            profile = profile.model_copy(
                update={
                    "write_paths": list(
                        dict.fromkeys(
                            [
                                *profile.write_paths,
                                *request.additional_write_paths,
                            ]
                        )
                    )
                }
            )

        if request.supervised_budget:
            max_steps = min(
                request.max_steps or profile.max_steps,
                40,
            )
            max_calls = min(
                request.max_model_calls or profile.max_model_calls,
                50,
            )
        else:
            max_steps = min(
                request.max_steps or profile.max_steps,
                profile.max_steps,
                self.settings.agent_max_steps,
            )
            max_calls = min(
                request.max_model_calls or profile.max_model_calls,
                profile.max_model_calls,
                self.settings.agent_max_model_calls,
            )

        normalized_messages = list(request.normalized_messages())
        session = AgentSession(
            id=secrets.token_urlsafe(18),
            request=request,
            profile=profile,
            messages=normalized_messages,
            trace=[],
            tools_used=[],
            model_calls=0,
            last_scores=[],
            final_route=None,
            final_provider=None,
            final_model=None,
            max_steps=max_steps,
            max_model_calls=max_calls,
            next_step=1,
            pending_approval_id=None,
            created_monotonic=time.monotonic(),
            excluded_routes=list(request.excluded_routes or []),
            project_context=None,
            protocol_retries=0,
            base_message_count=len(normalized_messages),
        )

        await self._bootstrap_context(session)

        suggestion = None
        if request.allow_deterministic_tools:
            suggestion = suggest_deterministic_tool(
                request.normalized_messages(),
                agent_id=profile.id,
            )
        if suggestion is not None:
            response = await self._run_deterministic_suggestion(
                session,
                suggestion,
            )
            if response is not None:
                return response

        return await self._continue(session)

    async def _continue(
        self,
        session: AgentSession,
    ) -> AgentResponse:
        for step in range(
            session.next_step,
            session.max_steps + 1,
        ):
            if session.model_calls >= session.max_model_calls:
                break

            response = await self.orchestrator.run(
                self._request(session)
            )
            session.model_calls += response.calls_used
            session.last_scores = response.routing_scores
            session.final_route = response.selected_route
            session.final_provider = response.selected_provider
            session.final_model = response.model
            raw = response.answer

            try:
                if session.request.response_protocol == "single_patch":
                    action = parse_single_patch_action(
                        raw,
                        session.request.single_file_path or "",
                        base_content=(
                            session.request.single_file_base_content or ""
                        ),
                        expected_sha256=(
                            session.request.single_file_base_sha256 or ""
                        ),
                    )
                elif session.request.response_protocol == "single_file":
                    action = parse_single_file_action(
                        raw,
                        session.request.single_file_path or "",
                        allow_plain_complete=(
                            response.selected_route in {"local_qwen", "local_expert"}
                            and response.finish_reason == "stop"
                        ),
                    )
                else:
                    action = parse_agent_action(raw)
            except AgentProtocolError as exc:
                session.protocol_retries += 1
                if (
                    response.selected_route in {"local_qwen", "local_expert"}
                    and session.request.routing_mode != "direct"
                    and response.selected_route not in session.excluded_routes
                ):
                    if (
                        session.request.response_protocol == "single_patch"
                        and session.local_protocol_repairs < 1
                    ):
                        # A patch is short and hash-bound. One in-session local
                        # format repair is safe and keeps local-only missions
                        # viable without opening a retry loop.
                        session.local_protocol_repairs += 1
                    elif self._has_eligible_alternative(
                        session,
                        response.selected_route,
                    ):
                        # Full-file/JSON repair needs a stronger fallback, and
                        # a second malformed patch cannot loop locally.
                        session.excluded_routes.append(response.selected_route)
                session.trace.append(
                    AgentStep(
                        step=step,
                        selected_route=response.selected_route,
                        provider=response.selected_provider,
                        model=response.model,
                        action="protocol_error",
                        reason=str(exc),
                        latency_ms=response.latency_ms,
                        raw_output=raw,
                    )
                )

                if (
                    session.protocol_retries
                    > self.settings.protocol_repair_max_retries
                ):
                    self._sessions.pop(session.id, None)
                    return self._response(
                        session,
                        (
                            f"{session.profile.name} agent protokolüne "
                            "uygun JSON üretemedi."
                        ),
                        "failed",
                    )

                if session.request.response_protocol == "single_patch":
                    expected = session.request.single_file_path or ""
                    base_sha256 = (
                        session.request.single_file_base_sha256 or ""
                    )
                    session.messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                "YAMA PROTOKOLÜ ONARIMI GEREKLİ.\n"
                                f"Hata: {exc}\n"
                                "Yolu ve hash değerini değiştirme. Taban "
                                "dosyada harfiyen tek kez bulunan daha küçük "
                                "bir SEARCH bloğu seç ve yalnızca şu zarfı döndür:\n"
                                f'<<<ADAM_PATCH path="{expected}" '
                                f'base_sha256="{base_sha256}">>>\n'
                                "<<<SEARCH>>>\nESKİ BLOK\n"
                                "<<<REPLACE>>>\nYENİ BLOK\n"
                                "<<<END_ADAM_PATCH>>>"
                            ),
                        )
                    )
                elif session.request.response_protocol == "single_file":
                    expected = session.request.single_file_path or ""
                    # Do not append the truncated source back into context. It
                    # wastes tokens and encourages the provider to repeat the
                    # same incomplete JSON payload.
                    session.messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                "DOSYA PROTOKOLÜ ONARIMI GEREKLİ.\n"
                                f"Hata: {exc}\n"
                                f"Beklenen dosya: {expected}\n"
                                "Cevabı kısalt, gereksiz açıklama ve uzun inline "
                                "stil kullanma. JSON veya Markdown üretme. "
                                "Dosyanın tamamını şu zarfla tek seferde döndür:\n"
                                f'<<<ADAM_FILE path="{expected}">>>\n'
                                "TAM HAM DOSYA İÇERİĞİ\n"
                                "<<<END_ADAM_FILE>>>"
                            ),
                        )
                    )
                else:
                    session.messages.extend(
                        [
                            ChatMessage(role="assistant", content=raw),
                            ChatMessage(
                                role="user",
                                content=(
                                    "PROTOKOL ONARIMI GEREKLİ.\n"
                                    f"Hata: {exc}\n"
                                    "Önceki cevabındaki niyeti koru fakat yalnızca "
                                    "tek bir geçerli JSON nesnesi döndür.\n"
                                    "Dosya oluşturma/değiştirme istendiyse final "
                                    "verme; workspace_write çağır.\n"
                                    "Geçerli örnek araç çağrısı:\n"
                                    '{"action":"tool","reason":"Dosyayı oluşturmak '
                                    'için.","tool":"workspace_write","arguments":'
                                    '{"path":"src/example.tsx","content":"..."}}\n'
                                    "Geçerli final örneği:\n"
                                    '{"action":"final","reason":"Görev tamamlandı.",'
                                    '"answer":"..."}'
                                ),
                            ),
                        ]
                    )
                session.next_step = step + 1
                continue

            if action.action == "need_context":
                if (
                    session.context_expansions
                    >= self.settings.agent_context_expansion_max_requests
                ):
                    session.messages.append(
                        ChatMessage(
                            role="user",
                            content=(
                                "CONTEXT_EXPANSION_DENIED: Bu oturumun "
                                "kademeli bağlam bütçesi doldu. Mevcut kanıta "
                                "dayan; doğrulanamayan noktayı finalde açıkla."
                            ),
                        )
                    )
                    session.next_step = step + 1
                    continue
                expanded = await self._expand_context(
                    session,
                    action.arguments or {},
                )
                session.trace.append(
                    AgentStep(
                        step=step,
                        selected_route=response.selected_route,
                        provider=response.selected_provider,
                        model=response.model,
                        action="context",
                        reason=action.reason,
                        tool="adaptive_context",
                        arguments=action.arguments,
                        tool_result=expanded,
                        latency_ms=response.latency_ms,
                        raw_output=raw,
                    )
                )
                session.messages.append(
                    ChatMessage(
                        role="user",
                        content=(
                            "CONTEXT_EXPANSION_APPLIED: İstenen doğrulanmış "
                            "bağlam AUTO_PROJECT_CONTEXT içine eklendi. "
                            "Şimdi göreve devam et."
                        ),
                    )
                )
                session.next_step = step + 1
                continue

            if (
                session.request.response_protocol in {
                    "single_file",
                    "single_patch",
                }
                and action.action == "tool"
                and action.tool == "workspace_write"
                and isinstance(action.arguments, dict)
            ):
                generated_path = str(
                    action.arguments.get("path") or ""
                )
                generated_content = action.arguments.get("content")
                if isinstance(generated_content, str):
                    contract_issue = _generated_source_contract_issue(
                        path=generated_path,
                        content=generated_content,
                        instruction=last_user_text(
                            session.request.normalized_messages()
                        ),
                    )
                    if contract_issue:
                        session.evidence_retries += 1
                        session.trace.append(
                            AgentStep(
                                step=step,
                                selected_route=response.selected_route,
                                provider=response.selected_provider,
                                model=response.model,
                                action="contract_rejected",
                                reason=contract_issue,
                                tool="source_contract_gate",
                                arguments={"path": generated_path},
                                latency_ms=response.latency_ms,
                                raw_output=None,
                            )
                        )
                        if (
                            session.evidence_retries
                            > self.settings
                            .agent_generated_evidence_max_retries
                        ):
                            self._sessions.pop(session.id, None)
                            return self._response(
                                session,
                                (
                                    "Üretilen test dosyası zorunlu Node test "
                                    f"sözleşmesini karşılamadı: {contract_issue}"
                                ),
                                "failed",
                            )
                        session.messages.append(
                            ChatMessage(
                                role="user",
                                content=(
                                    "SOURCE_CONTRACT_REJECTED: Dosya henüz "
                                    f"yazılmadı. {contract_issue} "
                                    "Aynı kesin yol için dosyanın tamamını "
                                    "protokole uygun yeniden üret."
                                ),
                            )
                        )
                        session.next_step = step + 1
                        continue
                    validation = (
                        await self.project_memory.validate_source_evidence(
                            path=generated_path,
                            content=generated_content,
                            allowed_missing_paths=(
                                session.request
                                .source_evidence_pending_paths
                            ),
                        )
                    )
                    if not validation.get("valid", False):
                        session.evidence_retries += 1
                        session.trace.append(
                            AgentStep(
                                step=step,
                                selected_route=response.selected_route,
                                provider=response.selected_provider,
                                model=response.model,
                                action="evidence_rejected",
                                reason=(
                                    "Üretilen yerel importlar doğrulanmış "
                                    "sembol indeksiyle uyuşmuyor."
                                ),
                                tool="source_evidence_gate",
                                arguments={"path": generated_path},
                                tool_result=validation,
                                latency_ms=response.latency_ms,
                                raw_output=None,
                            )
                        )
                        missing_paths = list(
                            validation.get(
                                "missing_context_paths",
                                [],
                            )
                        )
                        if (
                            missing_paths
                            and session.context_expansions
                            < self.settings
                            .agent_context_expansion_max_requests
                        ):
                            await self._expand_context(
                                session,
                                {
                                    "paths": missing_paths,
                                    "symbols": [],
                                },
                            )
                        if (
                            session.evidence_retries
                            > self.settings
                            .agent_generated_evidence_max_retries
                        ):
                            self._sessions.pop(session.id, None)
                            return self._response(
                                session,
                                (
                                    "Üretilen dosya doğrulanmamış yerel "
                                    "importlar içerdiği için yazılmadı. "
                                    f"Kanıt: {validation}"
                                ),
                                "failed",
                            )
                        session.messages.append(
                            ChatMessage(
                                role="user",
                                content=(
                                    "SOURCE_EVIDENCE_REJECTED: Dosya henüz "
                                    "yazılmadı. Olmayan export/sembol uydurma. "
                                    "Aşağıdaki yerel kanıta göre dosyanın "
                                    "tamamını yeniden üret:\n"
                                    + json.dumps(
                                        validation,
                                        ensure_ascii=False,
                                        default=str,
                                    )
                                ),
                            )
                        )
                        session.next_step = step + 1
                        continue

            if action.action == "final":
                known_paths: set[str] = set()
                if isinstance(session.project_context, dict):
                    tree = session.project_context.get("tree")
                    if isinstance(tree, dict):
                        for item in tree.get("entries", []):
                            if (
                                isinstance(item, dict)
                                and item.get("type") == "file"
                                and item.get("path")
                            ):
                                known_paths.add(str(item["path"]))

                    for file_data in session.project_context.get(
                        "files",
                        [],
                    ):
                        if (
                            isinstance(file_data, dict)
                            and file_data.get("path")
                        ):
                            known_paths.add(str(file_data["path"]))

                quality = inspect_agent_answer(
                    profile=session.profile,
                    answer=action.answer or "",
                    user_text=last_user_text(
                        session.request.normalized_messages()
                    ),
                    known_paths=known_paths,
                    known_agents=set(self.agents.ids()),
                    trace=session.trace,
                    planning_max_tasks=self.settings.planning_max_tasks,
                    planning_integrity_strict=(
                        self.settings.planning_integrity_strict
                    ),
                    delivery_status_guard_enabled=(
                        self.settings.delivery_status_guard_enabled
                    ),
                    execution_evidence_guard_enabled=(
                        self.settings.execution_evidence_guard_enabled
                    ),
                )

                if quality.accepted:
                    session.trace.append(
                        AgentStep(
                            step=step,
                            selected_route=response.selected_route,
                            provider=response.selected_provider,
                            model=response.model,
                            action="final",
                            reason=action.reason,
                            latency_ms=response.latency_ms,
                            raw_output=raw,
                        )
                    )
                    self._sessions.pop(session.id, None)
                    return self._response(
                        session,
                        action.answer or "",
                        "completed",
                    )

                session.trace.append(
                    AgentStep(
                        step=step,
                        selected_route=response.selected_route,
                        provider=response.selected_provider,
                        model=response.model,
                        action="quality_rejected",
                        reason=quality.reason,
                        latency_ms=response.latency_ms,
                        raw_output=raw,
                    )
                )

                if (
                    session.quality_retries
                    < self.settings.agent_quality_max_retries
                    and step < session.max_steps
                    and session.model_calls < session.max_model_calls
                ):
                    session.quality_retries += 1
                    if (
                        session.request.routing_mode != "direct"
                        and response.selected_route
                        not in session.excluded_routes
                        and self._has_eligible_alternative(
                            session,
                            response.selected_route,
                        )
                    ):
                        session.excluded_routes.append(
                            response.selected_route
                        )

                    session.messages.extend(
                        [
                            ChatMessage(role="assistant", content=raw),
                            ChatMessage(
                                role="user",
                                content=(
                                    "ROL KALİTE KONTROLÜ CEVABI REDDETTİ.\n"
                                    f"Neden: {quality.reason}\n"
                                    "Zorunlu çıktı sözleşmesindeki eksik "
                                    "bölümleri gerçek içerikle tamamla. "
                                    "Planner isen TASK biçimini harfiyen koru; "
                                    "kanıt, bağımlılık gerekçesi, agent ataması "
                                    "ve doğrulama alanlarını düzelt. "
                                    "Dosya yazma istendiyse başarılı "
                                    "workspace_write kanıtı olmadan final verme. "
                                    "Dosya yazdıysan Doğrulama Durumu alanı ver. "
                                    "Yaptığını söylemek yerine sonucu göster. "
                                    "Yalnızca geçerli agent JSON döndür."
                                ),
                            ),
                        ]
                    )
                    session.next_step = step + 1
                    continue

                self._sessions.pop(session.id, None)
                return self._response(
                    session,
                    (
                        f"{session.profile.name} rol sözleşmesini karşılayan "
                        f"bir cevap üretemedi. Son kalite hatası: "
                        f"{quality.reason}"
                    ),
                    "failed",
                )

            assert action.tool is not None
            session.tools_used.append(action.tool)

            try:
                fingerprint = tool_fingerprint(
                    action.tool,
                    action.arguments,
                )
                if (
                    fingerprint
                    in set(session.request.applied_tool_fingerprints)
                ):
                    result = {
                        "success": True,
                        "skipped": True,
                        "already_applied": True,
                        "tool": action.tool,
                        "fingerprint": fingerprint,
                        "reason": (
                            "Aynı işlem bu görevde daha önce başarıyla "
                            "uygulandı; yeniden onay veya araç çalıştırması "
                            "oluşturulmadı."
                        ),
                    }
                    success = True
                else:
                    self.agents.authorize(
                        profile=session.profile,
                        tool_name=action.tool,
                        arguments=action.arguments,
                    )
                    result = await self.tools.execute(
                        action.tool,
                        action.arguments,
                    )
                    success = True
            except ToolApprovalRequired as exc:
                session.messages.append(
                    ChatMessage(role="assistant", content=raw)
                )
                return self._pause(
                    session,
                    step,
                    exc.pending,
                    action.reason or "",
                    response.selected_route,
                    response.selected_provider,
                    response.model,
                    response.latency_ms,
                    raw,
                    action.arguments,
                )
            except (ToolError, ValueError, TypeError) as exc:
                result = {"error": str(exc)}
                success = False

            session.trace.append(
                AgentStep(
                    step=step,
                    selected_route=response.selected_route,
                    provider=response.selected_provider,
                    model=response.model,
                    action="tool",
                    reason=action.reason,
                    tool=action.tool,
                    arguments=action.arguments,
                    tool_result=result,
                    latency_ms=response.latency_ms,
                    raw_output=raw,
                )
            )
            session.messages.extend(
                [
                    ChatMessage(role="assistant", content=raw),
                    self._tool_message(action.tool, success, result),
                ]
            )
            session.next_step = step + 1

        self._sessions.pop(session.id, None)
        return self._response(
            session,
            f"{session.profile.name} adım/model sınırına ulaştı.",
            "max_steps",
        )

    def approval_application_snapshot(
        self,
        *,
        session_id: str,
        approval_id: str,
    ) -> AgentApprovalApplication | None:
        self._cleanup()
        item = self._approval_application_replays.get(
            (session_id, approval_id)
        )
        if item is None:
            return None
        return item[1]

    async def apply_approval(
        self,
        *,
        session_id: str,
        approval_id: str,
    ) -> AgentApprovalApplication:
        """
        Apply the approved tool exactly once and checkpoint the session
        before making another model request.
        """
        self._cleanup()

        replay = self.approval_application_snapshot(
            session_id=session_id,
            approval_id=approval_id,
        )
        if replay is not None:
            return replay

        async with self._session_lock(session_id):
            replay = self.approval_application_snapshot(
                session_id=session_id,
                approval_id=approval_id,
            )
            if replay is not None:
                return replay

            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(
                    "Agent oturumu bulunamadı veya süresi doldu."
                )
            if session.pending_approval_id != approval_id:
                replay = self.approval_application_snapshot(
                    session_id=session_id,
                    approval_id=approval_id,
                )
                if replay is not None:
                    return replay
                raise ValueError(
                    "Onay kimliği bu oturumla eşleşmiyor."
                )

            pending = await self.tools.approvals.get(approval_id)
            try:
                result = await self.tools.execute_approved(approval_id)
                success = True
            except (ToolError, ValueError, TypeError) as exc:
                result = {"error": str(exc)}
                success = False

            session.pending_approval_id = None
            if (
                session.trace
                and session.trace[-1].action == "approval_required"
            ):
                old = session.trace[-1]
                session.trace[-1] = old.model_copy(
                    update={
                        "action": "tool",
                        "reason": (
                            (old.reason or "")
                            + " Kullanıcı işlemi onayladı."
                        ).strip(),
                        "tool_result": result,
                    }
                )

            session.messages.append(
                self._tool_message(
                    pending.tool_name,
                    success,
                    result,
                )
            )
            session.max_steps = min(
                40,
                session.max_steps
                + self.settings.agent_post_approval_extra_steps,
            )
            session.max_model_calls = min(
                50,
                session.max_model_calls
                + self.settings.agent_post_approval_extra_model_calls,
            )

            application = AgentApprovalApplication(
                session_id=session_id,
                approval_id=approval_id,
                tool_name=pending.tool_name,
                success=success,
                result=result,
            )
            self._approval_application_replays[
                (session_id, approval_id)
            ] = (time.monotonic(), application)
            return application

    async def continue_after_approval(
        self,
        *,
        session_id: str,
    ) -> AgentResponse:
        """
        Continue the model loop after the tool result has already been
        checkpointed. A timeout here must never re-run the tool.
        """
        self._cleanup()
        async with self._session_lock(session_id):
            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(
                    "Agent oturumu bulunamadı veya süresi doldu."
                )
            if session.pending_approval_id is not None:
                raise ValueError(
                    "Agent oturumu hâlâ kullanıcı onayı bekliyor."
                )
            return await self._continue(session)

    async def abandon_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._session_locks.pop(session_id, None)

    async def approve(
        self,
        *,
        session_id: str,
        approval_id: str,
    ) -> AgentResponse:
        self._cleanup()

        async with self._approval_flow_lock(
            session_id,
            approval_id,
        ):
            replay = self._approval_replay(
                action="approve",
                session_id=session_id,
                approval_id=approval_id,
            )
            if replay is not None:
                return replay

            await self.apply_approval(
                session_id=session_id,
                approval_id=approval_id,
            )
            response = await self.continue_after_approval(
                session_id=session_id,
            )
            self._store_approval_replay(
                action="approve",
                session_id=session_id,
                approval_id=approval_id,
                response=response,
            )
            return response

    async def reject(
        self,
        *,
        session_id: str,
        approval_id: str,
    ) -> AgentResponse:
        self._cleanup()

        replay = self._approval_replay(
            action="reject",
            session_id=session_id,
            approval_id=approval_id,
        )
        if replay is not None:
            return replay

        async with self._session_lock(session_id):
            replay = self._approval_replay(
                action="reject",
                session_id=session_id,
                approval_id=approval_id,
            )
            if replay is not None:
                return replay

            session = self._sessions.get(session_id)
            if not session:
                raise ValueError(
                    "Agent oturumu bulunamadı veya süresi doldu."
                )
            if session.pending_approval_id != approval_id:
                replay = self._approval_replay(
                    action="reject",
                    session_id=session_id,
                    approval_id=approval_id,
                )
                if replay is not None:
                    return replay
                raise ValueError(
                    "Onay kimliği bu oturumla eşleşmiyor."
                )

            pending = await self.tools.approvals.get(approval_id)
            result = await self.tools.reject_approval(approval_id)
            session.pending_approval_id = None

            if (
                session.trace
                and session.trace[-1].action == "approval_required"
            ):
                old = session.trace[-1]
                session.trace[-1] = old.model_copy(
                    update={
                        "action": "tool_rejected",
                        "reason": (
                            (old.reason or "")
                            + " Kullanıcı işlemi reddetti."
                        ).strip(),
                        "tool_result": result,
                    }
                )

            session.messages.append(
                self._tool_message(
                    pending.tool_name,
                    False,
                    result,
                )
            )
            response = await self._continue(session)
            self._store_approval_replay(
                action="reject",
                session_id=session_id,
                approval_id=approval_id,
                response=response,
            )
            return response
