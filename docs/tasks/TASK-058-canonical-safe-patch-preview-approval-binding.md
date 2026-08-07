# TASK-058 - Canonical Safe Patch Preview and Approval Binding

Status: Completed
Branch: task-058-patch-preview-approval
Baseline: 32c147a1bd9c0c358054faf7a7c9152ff805e353

## Scope

TASK-058 provides a deterministic, read-only preview and immutable approval binding for an existing SafePatchPlan. It does not approve or execute changes.

## Completed contract

- Safe Patch Preview revision: `safe-patch-preview-v1`.
- Safe Patch Approval Binding revision: `safe-patch-approval-binding-v1`.
- SafePatchPlan remains machine-authoritative; approval IDs and versions identify the approval transaction, not patch content.
- The preview binds the bounded visible unified diff. The content-free binding binds workspace/project identity, repository map, scope lock, plan digest, preview digest and exact immutable operation snapshots.
- Preview alone does not authorize execution; binding alone does not prove human consent. Future authenticated approval infrastructure must associate its transaction with the binding digest.
- Exact change coverage, real `SafePatchPlan.assert_change()`, canonical operation ordering, initial/final freshness checks and independent raw pre-image fingerprints are enforced.
- Strict UTF-8, NUL rejection, create/replace/delete support, canonical `a/<path>`/`b/<path>` labels and bounded added/removed line metadata are implemented.
- Oversized previews fail closed; no hidden truncation, hidden tail approval or partial preview is possible.
- Project-root binding uses the supplied runtime snapshot; active project selection is not reread.
- TASK-056 and TASK-057 outputs feed directly into TASK-058; no executor adapter is required. SafePatchExecutor remains the sole mutation/rollback authority.
- ApprovalManager, PendingAction, ToolRegistry, WorkspaceWriteTool, Supervisor, core schemas, SafePatchPlan, SafePatchExecutor, structural compilers, Forge, Agent, UI and Pandora remain unchanged.
- No repository writes, temporary files, `.adam` artifacts, Git/subprocess, model/provider/network, CWD, Settings or dependency changes are part of TASK-058.
- Serialized preview and binding snapshots do not expose an absolute project root.

## Validation

- Targeted: `5 passed`.
- Focused patch/approval/security regression: `142 passed`.
- Final full suite: `902 passed`.
