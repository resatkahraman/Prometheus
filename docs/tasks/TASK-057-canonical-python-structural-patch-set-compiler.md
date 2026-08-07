# TASK-057 - Canonical Python Structural Patch Set Compiler

Status: Completed
Branch: task-057-structural-patch-set
Baseline: ae1613e5d2eae11e5b26cfbce8201d633fd24a2e

## Scope

TASK-057 composes multiple TASK-056 Python structural requests, including multiple non-overlapping edits in one file and edits across files, into one whole-file replacement per affected path and one real SafePatchPlan. It is read-only and does not execute the plan.

## Contract

Requests are grouped by canonical path, resolved against one original raw source/AST snapshot per file, validated for identity/indentation/line endings, rejected on duplicate selectors or overlap, then composed from descending original byte offsets. File and edit snapshots are immutable and hash/size-only. Outputs and changes are canonical path order; SafePatchPlan operation count equals affected file count and per-file stale fingerprints are verified.

TASK-058+ defers approval UI/API, Agent/Supervisor integration, automatic execution, Forge integration, natural-language generation and Git/commit integration.

## Final implementation

Python Structural Patch Set revision: `python-structural-patch-set-v1`.

The compiler is read-only, reuses TASK-056 request/selector semantics, bounds edits, groups by exact authorized path, reads and parses one original raw-byte source/AST per file, rejects duplicate semantic targets and overlaps, and composes non-overlapping edits in descending original-byte-offset order. Same-file edits and multiple Python files are supported; one whole-file `PatchChangeRequest` and one SafePatchPlan operation are emitted per affected file.

Decorator-aware spans, same-line safety, identity/indentation/encoding/line-ending rules and no-op rejection remain intact. Outputs are parsed, fingerprints are captured, per-file stale binding is checked after plan construction, and immutable hash/size-only snapshots bind the plan digest. No writes, temp files, executor calls, approval/tool exposure, Forge/Agent/Supervisor integration, Git, providers, global mutation or UI changes are added.

## Production correction

Initial targeted validation exposed one metadata-unpacking bug. The internal span tuple already carried `start_line` and `end_line`, but snapshot construction misnamed/discarded them, referenced undefined `e`, and used an ambiguous request variable. The tuple schema is now explicit and edit snapshots use named variables and keyword arguments. No tests were modified.

## Final validation

- Initial targeted: `2 failed, 2 passed`.
- Narrow regression: `2 passed`.
- Final targeted: `4 passed`.
- Focused structural/patch/security regression: `129 passed`.
- Final full suite: `897 passed, 1 existing warning` (exit code `0`).
- Warning: pre-existing Starlette/httpx TestClient deprecation warning; unrelated to TASK-057.
