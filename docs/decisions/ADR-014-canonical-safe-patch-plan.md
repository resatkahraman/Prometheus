# ADR-014 - Canonical Safe Patch Plan

Status: Accepted and completed

Prometheus represents proposed repository mutations as an immutable, deterministic `SafePatchPlan` bound to both the canonical RepositoryMap and ScopeLock. Each exact-file operation records only operation metadata, expected pre-image fingerprint/size, and proposed replacement fingerprint/size. The plan performs no writes and detects filesystem drift and execution-payload mismatch before later patch execution.

Scope Lock says where writes may occur, while this plan records what mutation is intended. WorkspaceWriteTool preview is an execution preview, and Forge's legacy `base_sha256` protocol is not a general repository patch manifest. Raw source/replacement content is excluded; one operation per path keeps v1 deterministic; byte-exact fingerprints detect stale files. AST/structural rewriting and actual writes are deferred.

## Validation

Initial targeted validation exposed two invalid test fixtures rather than production defects.

After fixture corrections:
- 2 narrow regression tests passed.
- 18 targeted Safe Patch Plan tests passed.
- 99 focused patch/security regression tests passed.
- 873 full-suite tests passed with 1 existing warning.

The warning is pre-existing and unrelated to TASK-054.
