# ADR-015 - Canonical Safe Patch Executor

Status: Accepted / Completed

SafePatchPlan is mandatory and the executor cannot widen ScopeLock. Full payload coverage is required. Replacements are staged and verified before mutation; existing pre-images receive temporary rollback material; a second stale check occurs after staging and each operation is checked immediately before commit.

Replace uses same-parent `os.replace`, create uses a no-clobber commit and never silently overwrites, and delete is exact-file only. Partial failures roll back in reverse order; unknown external content is never clobbered and incomplete rollback becomes explicit. TASK-055 does not claim crash-atomic or globally serializable multi-file transactions. Approval/tool/runtime integration and AST/structural mutation remain deferred.

## Validation

- 10 targeted Safe Patch Executor tests passed.
- 109 focused patch/security regression tests passed.
- 883 full-suite tests passed with 1 existing warning.

The warning is the pre-existing Starlette/httpx TestClient deprecation warning and is unrelated to TASK-055.

TASK-055 is not a crash-atomic multi-file transaction manager and does not claim global filesystem serializability.
