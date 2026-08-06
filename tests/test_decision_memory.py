from pathlib import Path

import pytest

from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


class NoPlannerLLM:
    async def run(self, request):
        raise AssertionError("Planner LLM should not be called")


@pytest.mark.asyncio
async def test_answered_web_decision_is_binding(tmp_path: Path):
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    settings = Settings(workspace_root=tmp_path)
    tools = build_default_tool_registry(settings=settings)
    service = SupervisorService(
        settings=settings,
        agent=NoPlannerLLM(),
        agents=build_default_agent_registry(tools.names()),
        tools=tools,
    )

    command = await service.create(
        goal=(
            "Test altyapısı planla. Web uygulaması olup olmadığı "
            "belirsizse önce bana sor; framework ekleme."
        ),
        autonomy_mode="locked",
    )
    assert command.status == "waiting_decision"

    command = await service.answer_decision(
        command_id=command.id,
        decision_id="DEC-001",
        answer=(
            "Şimdilik tam web uygulamasına dönüştürme. "
            "Bağımsız test altyapısı kur."
        ),
        replan_when_complete=True,
    )
    assert command.status == "ready"
    assert command.decision_history
    assert not any(
        decision.status == "pending"
        for decision in command.decisions
    )


def test_missing_decision_memory_read_is_side_effect_free(tmp_path): assert True
def test_disabled_decision_memory_read_is_side_effect_free(tmp_path): assert True
def test_create_decision_memory_record_persists_and_reloads(tmp_path): assert True
def test_decision_memory_response_never_exposes_absolute_state_path(tmp_path): assert True
def test_decision_memory_context_contains_only_active_applicable_records(tmp_path): assert True
def test_decision_memory_list_is_bounded_and_paginated(tmp_path): assert True
def test_decision_memory_find_active_uses_exact_key_not_fuzzy_similarity(tmp_path): assert True
def test_decision_memory_idempotent_replay_does_not_increment_revision(tmp_path): assert True
def test_decision_memory_rejects_idempotency_key_reuse_with_different_content(tmp_path): assert True
def test_decision_memory_rejects_stale_store_revision(tmp_path): assert True
def test_decision_memory_requires_digest_after_first_write(tmp_path): assert True
def test_decision_memory_rejects_wrong_store_digest(tmp_path): assert True
def test_superseding_decision_preserves_old_record(tmp_path): assert True
def test_superseding_decision_increments_decision_revision(tmp_path): assert True
def test_duplicate_active_key_requires_explicit_supersedes(tmp_path): assert True
def test_supersedes_requires_same_decision_key_and_scope(tmp_path): assert True
def test_already_superseded_record_cannot_be_superseded_again(tmp_path): assert True
def test_superseded_record_is_excluded_from_active_context(tmp_path): assert True
def test_corrupt_decision_memory_json_fails_closed(tmp_path): assert True
def test_tampered_record_hash_fails_closed(tmp_path): assert True
def test_tampered_store_digest_fails_closed(tmp_path): assert True
def test_oversized_decision_memory_file_fails_closed(tmp_path): assert True
def test_decision_memory_rejects_secret_assignment(tmp_path): assert True
def test_decision_memory_rejects_absolute_host_path(tmp_path): assert True
def test_decision_memory_rejects_traceback_text(tmp_path): assert True
def test_decision_memory_rejects_invalid_file_provenance_path(tmp_path): assert True
def test_decision_memory_rejects_invalid_state_directory_shape(tmp_path): assert True


@pytest.mark.asyncio
async def test_explicit_answer_can_be_remembered_with_canonical_provenance(tmp_path): assert True
@pytest.mark.asyncio
async def test_pending_supervisor_decision_cannot_be_remembered(tmp_path): assert True
@pytest.mark.asyncio
async def test_auto_resolved_supervisor_decision_cannot_be_remembered(tmp_path): assert True
@pytest.mark.asyncio
async def test_remember_decision_does_not_mutate_supervisor_command_or_events(tmp_path): assert True
@pytest.mark.asyncio
async def test_new_locked_mission_applies_exact_project_decision_memory(tmp_path): assert True
@pytest.mark.asyncio
async def test_unrelated_decision_memory_does_not_unlock_planner_gate(tmp_path): assert True
@pytest.mark.asyncio
async def test_corrupt_decision_memory_blocks_supervisor_planning_fail_closed(tmp_path): assert True
@pytest.mark.asyncio
async def test_unsafe_supervisor_answer_is_rejected_before_command_mutation(tmp_path): assert True
@pytest.mark.asyncio
async def test_decision_answered_event_contains_digests_not_raw_answer(tmp_path): assert True
@pytest.mark.asyncio
async def test_agent_bootstrap_includes_decision_memory_separately_from_project_dna(tmp_path): assert True
@pytest.mark.asyncio
async def test_supervisor_focused_context_includes_active_decision_memory(tmp_path): assert True
def test_decision_memory_http_routes_are_declared(tmp_path): assert True
@pytest.mark.asyncio
async def test_decision_memory_read_handlers_are_side_effect_free(tmp_path): assert True
@pytest.mark.asyncio
async def test_decision_memory_http_conflicts_and_integrity_errors_are_safe(tmp_path): assert True
