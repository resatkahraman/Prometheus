# TASK-056 - Canonical Python Structural Patch Compiler

Status: Completed
Branch: task-056-structural-patching
Baseline: 896524ae36d8356789cb802ed67d6c4bb52498cf

## Scope

TASK-056 is a read-only single-symbol Python structural compiler layered on TASK-050/052/053/054/055. It resolves one direct lexical function, async function or class with AST, replaces its exact physical source span textually, and compiles one SafePatchPlan operation without executing it.

## Contract

Selectors are immutable and direct-lexical; function-local nested symbols, ambiguity, kind mismatch and rename are rejected. Source is bounded raw BOM-free UTF-8 with LF/CRLF preservation. Decorators are included, indentation must match, replacement must contain one same-name/same-kind definition, and the full output is parsed again.

The compiler binds RepositoryMap membership, ScopeLock authorization and project identity, then uses SafePatchPlanBuilder and verifies that its pre-image matches the compiler observation. No writes, temp files, Forge shadow state, model calls or global mutation occur. TASK-057+ may address multiple edits, cross-file refactoring, structural frameworks and integration.

## Test plan

Local tests cover functions, methods, async/class symbols, decorators, ambiguity, encoding and line endings, identity, unchanged bytes, snapshot confidentiality, binding and plan creation.

## Final implementation

Python Structural Patch revision: `python-structural-patch-v1`.

The compiler is read-only and supports exactly function, async_function and class selectors. AST is used only for direct lexical semantic resolution and validation; original bytes remain authoritative for exact physical-span replacement. Decorators are included, unrelated bytes are preserved, replacement name/kind and indentation must match, and rename/create/delete are unsupported.

BOM-free UTF-8 with LF or CRLF is required; invalid UTF-8, BOM and mixed endings are rejected. Replacement line endings follow the target convention, full output is parsed, no-op replacements are rejected, and exact base/output/span fingerprints are captured. A real SafePatchPlanBuilder produces one replace operation and verifies the compiler's source pre-image. ScopeLock and RepositoryMap membership remain mandatory; no executor, Forge, tool, Agent/Supervisor, Git, provider, global mutation or UI integration is added.

## Production correction

Initial targeted validation exposed one narrow bytes/str indentation mismatch. `_line_info()` returns physical lines as bytes; indentation now strips with `b" \t"`, decodes only the resulting prefix as ASCII, and compares it with the string replacement indentation. No tests were modified and no architecture was weakened.

## Final validation

- Initial targeted: `6 failed, 4 passed`.
- Narrow regression: `6 passed`.
- Final targeted: `10 passed`.
- Focused structural/patch/security regression: `125 passed`.
- Final full suite: `893 passed, 1 existing warning` (exit code `0`).
- Warning: pre-existing Starlette/httpx TestClient deprecation warning; unrelated to TASK-056.
