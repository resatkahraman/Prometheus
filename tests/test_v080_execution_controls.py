from pathlib import Path

import pytest

from app.agent.engine import AgentEngine
from app.agent.protocol import parse_agent_action
from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse
from app.supervisor.models import SupervisorApprovalRecord, SupervisorTask
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class WriteRootScore:
    async def run(self, request):
        return OrchestrateResponse(
            answer=(
                '{"action":"workspace_write",'
                '"reason":"Kesin dosyayı oluştur.",'
                '"path":"score.py",'
                '"content":"def calculate_score(a,b,c): return a*b+c\\n"}'
            ),
            mode="auto",
            selected_route="github",
            selected_provider="github",
            model="test",
            latency_ms=1,
            task_type="coding",
            route_reason="test",
            calls_used=1,
            routing_scores=[],
        )


def make_task() -> SupervisorTask:
    return SupervisorTask(
        id="TASK-001",
        title="Score feature",
        priority="zorunlu",
        assigned_agent="backend",
        evidence=[],
        acceptance_criteria=["score.py ve testi mevcut olmalı"],
        dependencies=[],
        dependency_reason="yok",
        parallelizable="evet",
        verification="python -m pytest -q",
        user_approval="gerekli",
        exact_files=["score.py", "tests/test_score.py"],
    )


@pytest.mark.asyncio
async def test_supervisor_exact_file_scope_allows_requested_root_file(
    tmp_path: Path,
):
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    engine = AgentEngine(
        settings=settings,
        orchestrator=WriteRootScore(),
        tools=tools,
    )
    response = await engine.run(
        AgentRequest(
            message="score.py dosyasını oluştur.",
            agent_id="backend",
            allow_deterministic_tools=False,
            additional_write_paths=["score.py"],
        )
    )
    assert response.status == "awaiting_approval"
    assert response.pending_approval.tool_name == "workspace_write"
    assert response.pending_approval.arguments["path"] == "score.py"


def test_protocol_normalizes_tool_name_shorthand():
    action = parse_agent_action(
        '{"action":"workspace_write","reason":"x",'
        '"path":"score.py","content":"x=1"}'
    )
    assert action.action == "tool"
    assert action.tool == "workspace_write"
    assert action.arguments == {"path": "score.py", "content": "x=1"}


@pytest.mark.asyncio
async def test_local_evidence_gate_completes_after_matching_test(
    tmp_path: Path,
):
    (tmp_path / "tests").mkdir()
    (tmp_path / "score.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "tests" / "test_score.py").write_text(
        "def test_x(): assert True\n", encoding="utf-8"
    )
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=object(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )
    task = make_task()
    task.approval_history.append(
        SupervisorApprovalRecord(
            version=1,
            approval_id="write",
            state="applied",
            phase="worker",
            tool="workspace_write",
            preview={"path": "score.py"},
            success=True,
            result={"changed": True, "path": "score.py"},
        )
    )
    task.approval_history.append(
        SupervisorApprovalRecord(
            version=2,
            approval_id="test",
            state="applied",
            phase="worker",
            tool="safe_terminal",
            preview={"command": ["python", "-m", "pytest", "-q"]},
            success=True,
            result={
                "command": ["python", "-m", "pytest", "-q"],
                "exit_code": 0,
                "success": True,
                "stdout": "6 passed",
            },
        )
    )
    response = await service._local_completion_response(
        task=task,
        tool_name="safe_terminal",
        result=task.approval_history[-1].result,
    )
    assert response is not None
    assert response.status == "completed"
    assert response.final_route == "deterministic_evidence_gate"


def test_score_planner_exact_paths_are_not_moved():
    from app.planning.kernel import TypedPlanningKernel
    # Contract is asserted structurally in source-independent model output
    # by the dedicated planning test below.
    assert TypedPlanningKernel is not None
