import hashlib

import pytest

from app.agent.engine import AgentEngine
from app.agent.protocol import AgentProtocolError, parse_single_patch_action
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.tools.registry import build_default_tool_registry


def _request(base: str) -> AgentRequest:
    return AgentRequest(
        message="fix",
        response_protocol="single_patch",
        single_file_path="src/calc.py",
        single_file_base_content=base,
        single_file_base_sha256=hashlib.sha256(
            base.encode("utf-8")
        ).hexdigest(),
        exclusive_write_paths=["src/calc.py"],
    )


def test_hash_bound_patch_applies_one_exact_block() -> None:
    base = "def add(a, b):\n    return a - b\n"
    request = _request(base)
    raw = f'''<<<ADAM_PATCH path="src/calc.py" base_sha256="{request.single_file_base_sha256}">>>
<<<SEARCH>>>
    return a - b
<<<REPLACE>>>
    return a + b
<<<END_ADAM_PATCH>>>'''

    action = parse_single_patch_action(
        raw,
        "src/calc.py",
        base_content=base,
        expected_sha256=request.single_file_base_sha256 or "",
    )

    assert action.tool == "workspace_write"
    assert action.arguments == {
        "path": "src/calc.py",
        "content": "def add(a, b):\n    return a + b\n",
    }


def test_patch_rejects_stale_hash() -> None:
    base = "value = 1\n"
    request = _request(base)
    raw = f'''<<<ADAM_PATCH path="src/calc.py" base_sha256="{'0' * 64}">>>
<<<SEARCH>>>
value = 1
<<<REPLACE>>>
value = 2
<<<END_ADAM_PATCH>>>'''

    with pytest.raises(AgentProtocolError, match="beklenen dosya sürümüne"):
        parse_single_patch_action(
            raw,
            "src/calc.py",
            base_content=base,
            expected_sha256=request.single_file_base_sha256 or "",
        )


def test_patch_rejects_ambiguous_search() -> None:
    base = "pass\npass\n"
    request = _request(base)
    raw = f'''<<<ADAM_PATCH path="src/calc.py" base_sha256="{request.single_file_base_sha256}">>>
<<<SEARCH>>>
pass
<<<REPLACE>>>
return
<<<END_ADAM_PATCH>>>'''

    with pytest.raises(AgentProtocolError, match="tam bir kez"):
        parse_single_patch_action(
            raw,
            "src/calc.py",
            base_content=base,
            expected_sha256=request.single_file_base_sha256 or "",
        )


def test_single_patch_schema_rejects_mismatched_base() -> None:
    with pytest.raises(ValueError, match="uyuşmuyor"):
        AgentRequest(
            message="fix",
            response_protocol="single_patch",
            single_file_path="src/calc.py",
            single_file_base_content="value = 1\n",
            single_file_base_sha256="0" * 64,
        )


class _RepairingLocalOrchestrator:
    def __init__(self, sha256: str) -> None:
        self.sha256 = sha256
        self.requests = []

    async def run(self, request):
        self.requests.append(request)
        answer = "not a patch"
        if len(self.requests) == 2:
            answer = f'''<<<ADAM_PATCH path="src/calc.py" base_sha256="{self.sha256}">>>
<<<SEARCH>>>
return a - b
<<<REPLACE>>>
return a + b
<<<END_ADAM_PATCH>>>'''
        return OrchestrateResponse(
            answer=answer,
            mode="auto",
            selected_route="local_qwen",
            selected_provider="ollama",
            model="qwen3",
            finish_reason="stop",
            latency_ms=1,
            task_type="coding",
            route_reason="test",
            calls_used=1,
        )


@pytest.mark.asyncio
async def test_single_patch_allows_one_local_only_format_repair(
    tmp_path,
) -> None:
    base = "def add(a, b):\n    return a - b\n"
    sha256 = hashlib.sha256(base.encode()).hexdigest()
    orchestrator = _RepairingLocalOrchestrator(sha256)
    settings = Settings(
        _env_file=None,
        workspace_root=tmp_path,
        local_embedding_enabled=False,
    )
    engine = AgentEngine(
        settings=settings,
        orchestrator=orchestrator,
        tools=build_default_tool_registry(settings=settings),
    )

    response = await engine.run(
        AgentRequest(
            message="fix add",
            response_protocol="single_patch",
            single_file_path="src/calc.py",
            single_file_base_content=base,
            single_file_base_sha256=sha256,
            exclusive_write_paths=["src/calc.py"],
            allow_deterministic_tools=False,
        )
    )

    assert response.status == "awaiting_approval"
    assert len(orchestrator.requests) == 2
    assert "local_qwen" not in (
        orchestrator.requests[1].excluded_routes or []
    )
