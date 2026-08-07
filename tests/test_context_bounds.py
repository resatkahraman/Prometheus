from app.memory.context_bounds import ContextBounds, ContextPart
from types import SimpleNamespace


def test_supervisor_planner_bound_supports_legacy_partial_service_construction():
    from app.supervisor.service import SupervisorService

    service = SupervisorService.__new__(SupervisorService)
    service.project_dna = SimpleNamespace(
        context=lambda workspace_path: SimpleNamespace(text="PROJECT DNA marker")
    )
    prompt = service._planner_prompt("Implement feature")
    assert len(prompt) <= 24_000
    assert "PROJECT DNA marker" in prompt
    assert not hasattr(service, "settings")


def test_context_bounds_text_never_exceeds_limit():
    result = ContextBounds.bound_text("A" * 500, max_chars=80)
    assert result.chars == len(result.text) <= 80
    assert result.truncated


def test_context_bounds_same_input_produces_same_output_and_digest():
    assert ContextBounds.bound_text("x" * 200, max_chars=50) == ContextBounds.bound_text("x" * 200, max_chars=50)


def test_context_bounds_retains_head_and_tail_when_truncated():
    result = ContextBounds.bound_text("HEAD" + "x" * 100 + "TAIL", max_chars=60)
    assert "HEAD" in result.text and "TAIL" in result.text


def test_context_bounds_handles_limit_smaller_than_marker():
    assert ContextBounds.bound_text("abcdef", max_chars=2).chars == 2


def test_context_assembly_prioritizes_required_parts():
    result = ContextBounds.assemble([
        ContextPart("memory", "M" * 100, 1),
        ContextPart("evidence", "EVIDENCE", 100, True),
    ], max_chars=40)
    assert result.selected_part_ids[0] == "evidence"


def test_context_assembly_marks_required_overflow():
    result = ContextBounds.assemble([ContextPart("required", "x" * 100, 1, True)], max_chars=10)
    assert result.required_overflow and result.chars <= 10


def test_context_assembly_counts_separators_inside_budget():
    result = ContextBounds.assemble([ContextPart("a", "a", 1), ContextPart("b", "b", 1)], max_chars=3)
    assert result.chars <= 3
