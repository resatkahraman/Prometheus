# TASK-054 - Canonical Safe Patch Plan

Status: Completed
Branch: task-054-safe-patch-plan
Baseline: bb15db7eaabd49295095a50e86abfded3f6d1bb6

## Scope

TASK-054 defines a read-only immutable plan for exact-file create, replace and delete operations. It binds TASK-050 project identity, TASK-052 RepositoryMap and TASK-053 ScopeLock digests. No patch is generated or executed.

## Contract

`PatchChangeRequest`, `SafePatchOperationSnapshot` and `SafePatchPlanSnapshot` record canonical operation metadata, byte-exact pre-image hashes/sizes and UTF-8 replacement hashes/sizes without persisting content. The builder verifies map and scope integrity, project identity, complete map state, exact ScopeLock authorization, duplicate targets, operation limits and file-size bounds.

`SafePatchPlan.assert_current()` detects pre-image drift and rechecks ScopeLock symlink safety. `assert_change()` verifies a future executor's exact operation and replacement payload without writing. Create, replace and delete semantics remain explicit and no-op replacements are rejected.

## Test plan

Local tests cover deterministic ordering/digests, immutable snapshots, operation contracts, create/replace/delete state, scope and map binding, tamper detection, stale plans, payload matching, limits, read-only behavior and runtime binding. TASK-055+ will provide actual patch execution and structural engines.

## Final implementation

- Safe Patch Plan revision: `safe-patch-plan-v1`.
- Immutable request, operation and plan snapshot contracts.
- Explicit create/replace/delete semantics with deterministic canonical ordering and digest.
- TASK-050 identity, TASK-052 RepositoryMap and TASK-053 ScopeLock bindings with integrity verification.
- Real `ScopeLock.assert_write()` authorization for every target and one operation per canonical path.
- Bounded operation count and pre-image/replacement byte sizes.
- Exact raw-byte pre-image and UTF-8 replacement fingerprints; no-op replacements rejected.
- Stale mapped targets cannot silently become creates; `assert_current()` and `assert_change()` provide read-only verification.
- Source/replacement contents are not persisted and plan construction performs no writes, temp files, backups, shadow workspace or `.adam` artifacts.
- No Git, model/provider/network activity, CWD/global Settings mutation, ScopeLock/RepositoryMap/WorkspaceWriteTool/ToolRegistry/Agent/Supervisor/Forge/Pandora changes or dependency addition.

## Initial fixture correction

Initial targeted validation exposed two invalid test fixtures.

The digest-order test now builds both plans against identical filesystem pre-images, preserving caller-order-independent digests only when semantic inputs match. The existing-target-not-in-map test now creates ScopeLock while the future target is absent, then creates the file afterward to exercise SafePatchPlan's independent RepositoryMap membership defense without weakening TASK-053.

## Final validation

- Initial targeted: `2 failed, 16 passed`.
- Narrow regression after fixture correction: `2 passed`.
- Final targeted: `18 passed`.
- Focused patch/security regression: `99 passed`.
- Final full suite: `873 passed, 1 existing warning` (exit code `0`).
- Warning: pre-existing Starlette/httpx TestClient deprecation warning; unrelated to TASK-054.
