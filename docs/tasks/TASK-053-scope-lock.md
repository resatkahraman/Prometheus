# TASK-053 - Scope Lock

Status: Completed
Branch: task-053-scope-lock
Baseline: 92f47af6e266a72fc800b62123948ce178b7845e

## Scope

TASK-053 introduces an immutable, project-bound, fail-closed exact-file write scope rooted in a complete TASK-052 Repository Map snapshot. It does not integrate with current write tools, AgentEngine or SupervisorService.

## Contract

`ScopeLockSnapshot` records project identity, repository-map digest, canonical allowed/protected paths, write count and a canonical digest. `ScopeLockBuilder` verifies map integrity, completeness and project binding, normalizes paths through WorkspacePolicy, rejects protected or directory targets, requires existing targets to be map members, and supports explicitly scoped missing files.

`ScopeLock` enforces exact runtime matches, rechecks protected paths and symlink resolution, and provides an immutable snapshot. Empty scopes are explicit deny-all locks. No source contents, Git, provider calls or global active-project state are consulted.

## Test plan

Local deterministic tests cover canonical ordering/digests, deny-all behavior, integrity and completeness failures, project binding, existing/new targets, protected precedence, unsafe paths, exact runtime authorization, runtime binding and mutation guards.

## Final implementation

- Scope Lock revision: `scope-lock-v1`.
- Immutable `ScopeLockSnapshot` with exact-file authorization only.
- Canonical project-relative POSIX paths with deterministic sorted/deduplicated allowed and protected paths.
- Deterministic canonical JSON digest and explicit empty deny-all scope.
- TASK-050 runtime/project snapshot binding and TASK-052 RepositoryMap integrity validation.
- Incomplete maps fail closed; protected paths and RepositoryMap protected annotations remain authoritative.
- Existing writable files must belong to the canonical map; explicitly scoped missing files are supported.
- WorkspacePolicy remains the confinement/security authority; sensitive paths and symlink aliases cannot widen scope.
- Runtime checks revalidate symlink safety and active-project changes cannot retarget a builder or lock.
- No source-file reads, Git subprocesses, model/provider/network activity, CWD/global Settings mutation, AgentAccessController, WorkspaceWriteTool, ToolRegistry, SupervisorService or Pandora/UI changes, and no dependency addition.

## Implementation correction

Initial targeted validation exposed two production contract defects and two invalid test fixtures.

Production corrections:
- `ScopeLockSnapshot` now stores `tuple[str, ...]` rather than lists.
- Leading `./` paths normalize to the same canonical exact path.

Test corrections:
- Incomplete RepositoryMap cases now use legitimately bounded `RepositoryMapBuilder` snapshots instead of stale-digest mutations.
- The component-aware fixture creates its parent directory correctly.

## Final validation

- Initial targeted: `6 failed, 16 passed`.
- Narrow regression after correction: `7 passed`.
- Final targeted: `23 passed`.
- Focused security regression: `93 passed`.
- Final full suite: `855 passed, 1 existing warning` (exit code `0`).
- Warning: pre-existing Starlette/httpx TestClient deprecation warning; unrelated to TASK-053.
