from dataclasses import replace
import json
import pytest
from app.improvement.approved_patch_binding import SelfDevelopmentApprovedPatchBinder, SelfDevelopmentApprovedPatchBindingAuthorizationError, SelfDevelopmentApprovedPatchBindingIntegrityError, SelfDevelopmentApprovedPatchBindingProjectError
from app.improvement.decision_gate import SelfDevelopmentDecisionGate
from app.improvement.human_decision import SelfDevelopmentHumanDecisionBinder
from app.improvement.promotion_authority import SelfDevelopmentPromotionAuthorityIssuer
from app.workspace.patch_approval import SafePatchApprovalBuilder
from app.workspace.patch_plan import PatchChangeRequest, SafePatchPlanBuilder
from app.workspace.repository_map import RepositoryMapBuilder
from app.workspace.scope_lock import ScopeLockBuilder
from tests.test_self_development_decision_gate import make_evaluation

def make_patch(tmp_path, filename="a.py", replacement="x = 2\n"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / filename).write_text("x = 1\n", encoding="utf-8")
    repo = RepositoryMapBuilder(project_root=tmp_path, workspace_path="ws", project_key="project-a").build()
    lock = ScopeLockBuilder(project_root=tmp_path, workspace_path="ws", project_key="project-a").build(repository_map=repo, allowed_write_paths=[filename])
    change = PatchChangeRequest(filename, "replace", replacement)
    plan = SafePatchPlanBuilder(project_root=tmp_path, workspace_path="ws", project_key="project-a").build(repository_map=repo, scope_lock=lock, changes=[change])
    approval = SafePatchApprovalBuilder(project_root=tmp_path, workspace_path="ws", project_key="project-a").prepare(plan=plan, changes=[change]).binding
    return plan, approval

@pytest.mark.asyncio
async def test_valid_binding_is_deterministic_and_exact(tmp_path):
    evaluation = await make_evaluation(tmp_path)
    gate = SelfDevelopmentDecisionGate(project_key="project-a").decide(evaluation=evaluation)
    authority = SelfDevelopmentPromotionAuthorityIssuer(project_key="project-a").issue(decision=SelfDevelopmentHumanDecisionBinder(project_key="project-a").bind(gate=gate, decision="approve"))
    plan, approval = make_patch(tmp_path)
    binder = SelfDevelopmentApprovedPatchBinder(project_key="project-a")
    first = binder.bind(authority=authority, plan=plan, approval=approval)
    assert first == binder.bind(authority=authority, plan=plan, approval=approval)
    assert first.binding_scope == "self-development-approved-patch" and first.promotion_execution_eligible is True
    assert first.source_mutation_allowed is False and first.main_branch_mutation_allowed is False

@pytest.mark.asyncio
async def test_substitution_project_and_tamper_fail_closed(tmp_path):
    evaluation = await make_evaluation(tmp_path)
    gate = SelfDevelopmentDecisionGate(project_key="project-a").decide(evaluation=evaluation)
    authority = SelfDevelopmentPromotionAuthorityIssuer(project_key="project-a").issue(decision=SelfDevelopmentHumanDecisionBinder(project_key="project-a").bind(gate=gate, decision="approve"))
    plan, approval = make_patch(tmp_path)
    binder = SelfDevelopmentApprovedPatchBinder(project_key="project-a")
    with pytest.raises(SelfDevelopmentApprovedPatchBindingIntegrityError): binder.bind(authority=replace(authority, promotion_authorized=False), plan=plan, approval=approval)
    with pytest.raises(SelfDevelopmentApprovedPatchBindingProjectError): SelfDevelopmentApprovedPatchBinder(project_key="other").bind(authority=authority, plan=plan, approval=approval)
    with pytest.raises(SelfDevelopmentApprovedPatchBindingIntegrityError): binder.bind(authority=authority, plan=plan, approval=replace(approval, plan_digest="sha256:" + "0" * 64))
    plan_b, approval_b = make_patch(tmp_path / "plan_b", filename="b.py", replacement="x = 3\n")
    with pytest.raises(SelfDevelopmentApprovedPatchBindingAuthorizationError): binder.bind(authority=authority, plan=plan, approval=approval_b)
    serialized = json.dumps(binder.bind(authority=authority, plan=plan, approval=approval).to_dict())
    assert all(value not in serialized for value in ("C:\\secret-host-path", "RAW_PATCH_SECRET", "api_key=", "Bearer", "human rationale secret"))
