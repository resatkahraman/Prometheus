# ADR-017 - Canonical Python Structural Patch Set Compiler

Status: Accepted / Completed

SafePatchPlan rejects duplicate paths, so TASK-057 composes multiple non-overlapping structural edits against one original source/AST snapshot per file. All targets resolve before descending byte-offset composition; one whole-file replacement is emitted per affected path and cross-file outputs compose into one deterministic plan. Overlap, including class/member ancestor overlap, is rejected rather than ordered; TASK-057 provides no conflict resolution.

The compiler is read-only and preserves unrelated bytes. SafePatchExecutor remains separate. Approval, integration and further structural execution belong to TASK-058+.

## Validation

- Initial targeted run exposed one edit-snapshot tuple-unpacking defect: `2 failed, 2 passed`.
- Narrow regression after the production fix: `2 passed`.
- Final targeted structural patch-set suite: `4 passed`.
- Focused structural/patch/security regression: `129 passed`.
- Final full suite: `897 passed` with 1 existing warning.

The warning is the pre-existing Starlette/httpx TestClient deprecation warning and is unrelated to TASK-057.

SafePatchPlan duplicate-path protection remains intact. Multiple same-file edits resolve against one original source/AST and compose by descending original offsets; overlap is rejected rather than ordered. One operation is produced per file, and SafePatchExecutor remains the separate execution/rollback layer. No general conflict-resolution or refactoring engine is claimed.
