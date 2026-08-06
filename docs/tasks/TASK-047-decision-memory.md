Exit code: 0
Wall time: 0.3 seconds
Output:
# TASK-047 â€” Decision Memory

Status: Completed and validated.

## Objective and scope

Decision Memory stores only explicitly confirmed decisions in Prometheus-owned runtime state.

## Architecture

Each selected project uses `.adam/decision_memory.json`. The store is schema-versioned, bounded, hash-verified, root-scoped and protected by in-process locking.

## Storage and integrity

Records and the store digest are verified on every read. Corruption, unsupported shapes and tampering fail closed.

## Explicit write contract

Writes require `confirmation="record_decision"`, provenance, idempotency and optimistic-concurrency preconditions.

## Supersession

Superseding creates a new immutable record and preserves the previous record.

## Supervisor integration

Only explicitly answered, non-auto-resolved Supervisor decisions may be remembered.

## Context integration

Active exact-key decisions may be supplied as a separate read-only context source.

## HTTP API

List, read, explicit create and Supervisor remember routes use existing authentication, CSRF protection and no-store responses.

## Security guarantees

Bounds, unsafe text, secrets, paths, private-key material and malformed state are rejected without leaking raw values.

## Known limitations

No fuzzy, vector, graph or multi-process file locking is included. Delete, forget and edit APIs are not provided.

## Validation

<!-- TASK-047-VALIDATION-RESULTS -->

## Final validation

- Task-specific tests: `42 passed`.
- Focused Decision Memory regression: `150 passed, 1 warning`.
- Final full suite: `743 passed, 1 warning`.
- Static validation: `py_compile` and AST checks passed.
- Whitespace validation: `git diff --check` passed.
- Warning: existing Starlette TestClient/httpx deprecation warning; no failures.
- No Pandora, UI or dependency changes.
