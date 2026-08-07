# TASK-052 - Canonical Repository Map

Status: Completed
Branch: task-052-repository-map
Baseline: e6047f78bdec4f26a5c0eacb6a460fa6273c9513

## Scope

TASK-052 introduces a deterministic, immutable, metadata-only inventory of a selected TASK-050 Project Workspace. It does not index source contents, parse ASTs, build import or symbol graphs, summarize with a model, or integrate with prompts.

## Contract

`RepositoryMapSnapshot` contains the revision, workspace identity, bounded canonical entries, entry/depth truncation flags and a SHA-256 digest of canonical JSON metadata. Entries use project-relative POSIX paths, deterministic role classification, file suffix, size, depth and optional key/protected annotations.

Traversal is lexical, bounded, project-scoped and symlink-safe. The exact internal/generated directory set is ignored. WorkspacePolicy is reused for confinement and sensitive-path protection. Long paths and mapping races fail closed with stable safe errors.

The builder can be created from a TASK-050 runtime snapshot and remains bound to that runtime's project root, workspace path and project key. Future TASK-053+ scope-lock, safe-patching and structural validation systems are the intended consumers.

## Test plan

Local deterministic tests cover ordering, digest stability, relative serialization, role classification, ignored directories, entry/depth/path bounds, empty projects, annotations, symlinks, project isolation, runtime binding and mutation guards.

## Final implementation

- Canonical Repository Map revision: `repository-map-v1`.
- Metadata-only repository inventory with project-relative POSIX paths.
- Deterministic lexical ordering and canonical JSON digest.
- Hard entry, depth and relative-path-length limits.
- Symlink-safe traversal and generated/internal directory exclusions.
- Source, test, config, docs and other classification.
- Component-aware Project DNA key-path and protected-path annotations.
- TASK-050 runtime snapshot binding with no active-project reread after construction.
- No source-file content reads, Git subprocesses, model/provider/network calls or global mutable state.
- No Pandora/UI changes and no dependency addition.

## Narrow implementation correction

The first targeted run found that `RepositoryMapSnapshot.entries` contained serialized dictionaries rather than immutable `RepositoryMapEntry` objects. The producer was corrected so the in-memory snapshot now stores `tuple[RepositoryMapEntry, ...]`, while serialization remains confined to `to_dict()` and digest payload construction.

## Final validation

- Initial targeted: `11 failed, 7 passed`.
- Narrow regression after correction: `4 passed`.
- Final targeted: `18 passed`.
- Focused regression: `77 passed, 1 existing warning`.
- Final full suite: `832 passed, 1 existing warning` (exit code `0`).
- Warning: pre-existing Starlette/httpx TestClient deprecation warning; unrelated to TASK-052.
