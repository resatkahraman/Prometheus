# ADR-004 — Deterministic Failure Classification and Bounded Recovery

Status: Accepted

## Context

Mission execution needs an auditable recovery mechanism without creating a parallel runtime, producing synthetic receipts, or delegating safety decisions to a model.

## Decision

Mission failures are classified deterministically from stable runtime signals. Recovery is explicit, user-triggered, checkpointed, bounded, idempotent, and executed only through the existing Supervisor scheduling path. Integrity, policy, approval rejection, cancellation, internal, and unknown failures remain fail-closed.

## Consequences

- Classification performs no model or provider calls.
- There is no automatic retry loop.
- At most one recovery is accepted per failure ID and three per Mission.
- Every accepted recovery appends an immutable, non-resumable pre-recovery checkpoint.
- Real retries retain their normal immutable Execution Receipts.
- The canonical Mission Event Journal preserves classification and recovery history.
- Existing task/runtime attempt limits remain authoritative.
