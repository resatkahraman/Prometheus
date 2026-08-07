# ADR-016 - Canonical Python Structural Patch Compiler

Status: Accepted / Completed

TASK-056 uses the standard-library `ast` module for semantic targeting and original source text for exact span replacement. Direct lexical selectors resolve one function, async function or class; function-local descent and same-name ambiguity fail closed. Decorators are included in physical spans, formatting and unrelated bytes are preserved, and replacement identity requires the same name and kind.

The compiler requires BOM-free UTF-8, preserves LF/CRLF conventions, performs no auto-indentation or `ast.unparse`, and creates a real SafePatchPlan without writes. A critical base-hash guard prevents stale structural output from rebinding to a changed source. It is not a general refactoring engine: rename, cross-file edits, import rewriting and AST/CST transformations are deferred. Forge and SafePatchExecutor remain separate.

## Validation

- Initial targeted run exposed one bytes/str indentation bug: `6 failed, 4 passed`.
- Narrow regression after the production fix: `6 passed`.
- Final targeted structural patch suite: `10 passed`.
- Focused structural/patch/security regression: `125 passed`.
- Final full suite: `893 passed` with 1 existing warning.

The warning is the pre-existing Starlette/httpx TestClient deprecation warning and is unrelated to TASK-056.

The stdlib AST remains semantic-only; source bytes preserve formatting, no automatic reformatting or CST dependency is used, and SafePatchPlan/SafePatchExecutor remain separate layers.
