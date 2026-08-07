# ADR-012 - Canonical Repository Map

Status: Accepted and completed

Prometheus uses one deterministic, project-scoped, metadata-only repository map as the canonical structural inventory for future scope-lock and safe-patching systems. Mapping operates on a TASK-050 Project Workspace snapshot, reuses WorkspacePolicy confinement, never follows symlinks, never reads file contents, and is explicitly bounded by entry, depth and path limits.

Ad-hoc traversal is insufficient for self-development, and the Git index cannot be the canonical source for a live filesystem snapshot. Source-content indexing and AST mapping are intentionally deferred. The mapper is bound to its runtime snapshot and does not consult active-project state after construction.

The map records canonical relative paths, deterministic roles, file sizes, bounded depth, key/protected annotations and a canonical metadata digest. Later TASK-053+ work may consume this contract for scope lock and safe patching.

## Validation

Initial targeted exposed one in-memory entry-type contract defect.
Narrow correction regression: `4 passed`.
Final targeted repository-map suite: `18 passed`.
Focused workspace/repository regression: `77 passed, 1 existing warning`.
Full suite: `832 passed, 1 existing warning`.
The warning is pre-existing and unrelated to TASK-052.
