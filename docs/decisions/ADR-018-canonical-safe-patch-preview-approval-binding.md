# ADR-018 - Canonical Safe Patch Preview and Approval Binding

Status: Accepted / Completed

SafePatchPlan.digest remains the canonical machine mutation identity. Approval IDs and versions identify the approval transaction, not patch content. SafePatchPreview binds exactly the bounded unified diff shown to a user, while SafePatchApprovalBinding binds the plan, preview, project/map/scope identity and exact operation fingerprints without storing source or replacement content. Oversized previews fail closed and are never silently truncated. Prepare and assert_binding recheck pre-images; stale and mismatch errors remain distinct. The binding does not prove human consent or authorize execution by itself. Future transaction integration must explicitly associate approval state with the binding digest.

SafePatchExecutor remains a separate mutation authority. Generic ApprovalManager, ToolRegistry, WorkspaceWriteTool and Supervisor remain unchanged in TASK-058.

Validation:
- Targeted Safe Patch Approval suite: 5 passed.
- Focused patch/approval/security regression: 142 passed.
- Final full suite: 902 passed.
