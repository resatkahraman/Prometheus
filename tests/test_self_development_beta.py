from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.improvement.self_development_beta import (
    BETA_VERSION,
    BetaIntegrityError,
    BetaPhase,
    BetaScopeError,
    BetaValidationError,
    SelfDevelopmentBetaOrchestrator,
    SelfDevelopmentBetaRequest,
    SelfDevelopmentBetaStore,
)


def request(tmp_path: Path, **changes):
    values = {
        "request_id": "req-074",
        "workspace_path": str(tmp_path.resolve()),
        "project_key": "prometheus",
        "objective": "Fix a contained deterministic regression in the parser.",
        "trusted_objective_source": "operator",
        "context_refs": ("episode-1",),
        "maximum_scope": ("app/parser.py", "tests/test_parser.py"),
        "requested_risk_class": "low",
        "created_at": "2026-08-12T00:00:00+00:00",
    }
    values.update(changes)
    return SelfDevelopmentBetaRequest(**values)


def service(tmp_path: Path):
    return SelfDevelopmentBetaOrchestrator(store=SelfDevelopmentBetaStore(root=tmp_path / "beta-state"))


def test_valid_bounded_request_and_deterministic_identity(tmp_path):
    first = request(tmp_path)
    second = request(tmp_path)
    assert first.digest == second.digest
    assert first.beta_version == BETA_VERSION


@pytest.mark.parametrize("objective", ["rewrite Prometheus", "optimize everything", "change security policy"])
def test_broad_or_sensitive_objective_fails_closed(tmp_path, objective):
    with pytest.raises(BetaScopeError):
        request(tmp_path, objective=objective)


def test_workspace_escape_fails_closed(tmp_path):
    with pytest.raises(BetaScopeError):
        request(tmp_path, workspace_path=str(tmp_path / ".." / "outside"))


@pytest.mark.parametrize("risk", ["high", "unknown", "critical"])
def test_unknown_and_high_risk_rejected(tmp_path, risk):
    with pytest.raises(BetaValidationError):
        request(tmp_path, requested_risk_class=risk)


def test_model_output_cannot_be_objective_authority(tmp_path):
    with pytest.raises(BetaValidationError):
        request(tmp_path, trusted_objective_source="model")


def test_start_is_requested_and_replay_safe(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    assert run.phase is BetaPhase.REQUESTED
    assert svc.start(request(tmp_path)).beta_run_id == run.beta_run_id


def test_canonical_chain_requires_every_ordered_stage(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    run = svc.record_proposal(run.beta_run_id, "sp_proposal")
    run = svc.record_evidence(run.beta_run_id, "ser_evidence")
    run = svc.record_candidate(run.beta_run_id, "sdc_candidate")
    run = svc.record_evaluation(run.beta_run_id, "sde_eval")
    with pytest.raises(BetaValidationError):
        svc.record_verification(run.beta_run_id, "spv_wrong")
    assert run.phase is BetaPhase.EVALUATION_READY


def test_decision_gate_cannot_be_skipped(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    for method, value in ((svc.record_proposal, "p"), (svc.record_evidence, "e"), (svc.record_candidate, "c"), (svc.record_evaluation, "v")):
        run = method(run.beta_run_id, value)
    run = svc.require_decision(run.beta_run_id)
    assert run.phase is BetaPhase.DECISION_REQUIRED
    assert run.status == "blocked"


def test_promotion_binding_requires_decision(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    with pytest.raises(BetaValidationError):
        svc.record_promotion_binding(run.beta_run_id, "binding")


def test_approval_identity_is_recorded_not_created(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    for method, value in ((svc.record_proposal, "p"), (svc.record_evidence, "e"), (svc.record_candidate, "c"), (svc.record_evaluation, "v")):
        run = method(run.beta_run_id, value)
    svc.require_decision(run.beta_run_id)
    run = svc.record_decision(run.beta_run_id, "sdh_approval")
    assert run.phase is BetaPhase.PROMOTION_APPROVAL_REQUIRED
    assert run.decision_id == "sdh_approval"


def test_execution_and_verification_are_distinct(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    for method, value in ((svc.record_proposal, "p"), (svc.record_evidence, "e"), (svc.record_candidate, "c"), (svc.record_evaluation, "v")):
        run = method(run.beta_run_id, value)
    svc.require_decision(run.beta_run_id)
    svc.record_decision(run.beta_run_id, "d")
    svc.record_promotion_binding(run.beta_run_id, "b")
    run = svc.record_execution(run.beta_run_id, "receipt")
    assert run.phase is BetaPhase.PROMOTION_EXECUTED
    run = svc.record_verification(run.beta_run_id, "verification")
    assert run.phase is BetaPhase.POST_PROMOTION_VERIFIED


def test_git_approval_and_integration_are_last_authority_stages(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    for method, value in ((svc.record_proposal, "p"), (svc.record_evidence, "e"), (svc.record_candidate, "c"), (svc.record_evaluation, "v")):
        run = method(run.beta_run_id, value)
    svc.require_decision(run.beta_run_id); svc.record_decision(run.beta_run_id, "d"); svc.record_promotion_binding(run.beta_run_id, "b")
    svc.record_execution(run.beta_run_id, "x"); svc.record_verification(run.beta_run_id, "vfy")
    run = svc.require_git_approval(run.beta_run_id)
    assert run.phase is BetaPhase.GIT_APPROVAL_REQUIRED
    run = svc.record_git_approval(run.beta_run_id, "git-approval")
    run = svc.record_git_integration(run.beta_run_id, "git-receipt")
    run = svc.complete(run.beta_run_id)
    assert run.phase is BetaPhase.COMPLETED


def test_terminal_replay_does_not_repeat_integration(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    run = svc.record_proposal(run.beta_run_id, "p")
    assert svc.resume(run.beta_run_id).phase is BetaPhase.PROPOSAL_READY


def test_restart_recovers_exact_phase(tmp_path):
    run = service(tmp_path).start(request(tmp_path))
    restarted = SelfDevelopmentBetaOrchestrator(store=SelfDevelopmentBetaStore(root=tmp_path / "beta-state"))
    assert restarted.resume(run.beta_run_id).request_digest == run.request_digest


def test_corrupt_durable_state_fails_closed(tmp_path):
    store = SelfDevelopmentBetaStore(root=tmp_path / "state")
    run = service(tmp_path).start(request(tmp_path))
    path = store._path(run.beta_run_id)
    path.write_text(json.dumps({"phase": "requested", "digest": "sha256:" + "0" * 64}), encoding="utf-8")
    with pytest.raises(BetaIntegrityError):
        store.load(run.beta_run_id)


def test_invalid_artifact_ids_fail_closed(tmp_path):
    svc = service(tmp_path)
    run = svc.start(request(tmp_path))
    with pytest.raises(BetaValidationError):
        svc.record_proposal(run.beta_run_id, "bad id")


def test_no_generic_executor_or_process_authority():
    source = Path("app/improvement/self_development_beta.py").read_text(encoding="utf-8")
    assert "subprocess" not in source
    assert "Command(" not in source
    assert "git push" not in source


def test_no_remote_publication_or_pandora_mutation():
    source = Path("app/improvement/self_development_beta.py").read_text(encoding="utf-8")
    assert "write_text" not in source
    assert "Path(self.workspace_path).write" not in source
