# TASK-043 — Mission Recovery and Error Classification

Status: Completed and validated.

Baseline commit: `a5d89514ad10ba8eb66d5127475e089edb25e84f`

## Objective

Add deterministic, Prometheus-owned failure classification and explicit bounded Mission recovery while reusing the canonical event journal, immutable execution receipts, Mission checkpoints, command locks, background jobs, and existing Supervisor execution path.

## Files

Production changes are limited to the Supervisor recovery module, models, service, canonical event-kind mapping, and HTTP routes. Tests live in `tests/test_mission_recovery.py`. Project status, roadmap, this task record, and ADR-004 record the decision.

## Taxonomy

Failures are classified from stable runtime signals into transient provider, rate limit, timeout, dependency unavailable, verification failure, approval rejection, policy block, state conflict, integrity failure, cancellation, invalid request, internal error, or unknown. Classification is deterministic and never model-based.

## Bounded manual recovery

Recovery requires an explicit user request. Exactly one recovery is accepted per failure ID and no more than three per Mission. Duplicate accepted requests are idempotent. Policy, approval rejection, integrity, state conflict, cancellation, invalid request, internal error, and unknown classifications fail closed.

## Ordering

A real terminal execution writes its real receipt and normal terminal events before `mission_failure_classified`. Accepted recovery appends a non-resumable immutable system checkpoint before recovery events and scheduling. The retry executes only through `advance(..., background=True)` and therefore retains normal execution receipts. Completion or another classified failure is journaled after the retry's ordinary terminal evidence.

## Security guarantees

Failure messages are bounded and redact secrets, traceback material, and absolute host paths. Recovery cannot override task, provider, checkpoint, retry count, autonomy, or background mode. Integrity failures are neither repaired nor retried. Read status is side-effect-free.

## Known limitations

There is no automatic retry loop, distributed/multi-process recovery coordination, corruption repair, arbitrary journal replay, or historical checkpoint rollback. Runtime attempt limits remain authoritative. Mission History and post-run summaries are deferred to TASK-044.

Antigravity performed no Git operations and ran no tests for this implementation.

Next task: TASK-044 — Mission History and Post-Run Summary.
## Validation results

- Focused validation: `111 passed, 1 warning`
- Targeted regression validation: `40 passed`
- Final full-suite validation: `593 passed, 1 warning`
