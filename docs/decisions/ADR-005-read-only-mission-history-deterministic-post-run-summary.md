# ADR-005 — Read-Only Mission History and Deterministic Post-Run Summary

Status: Accepted

## Decision

Mission History is a read-only projection whose ordering spine is the canonical Mission Event Journal. Immutable receipts and checkpoints enrich journal events through verified references. Post-run summaries are deterministic projections and are not persisted as a second source of truth.

## Consequences

- No model or provider generates summaries.
- No new history database or persistent summary store exists.
- Event sequence remains the pagination cursor.
- Raw event payloads are not public history output.
- Missing or mismatched references fail closed.
- Unlinked immutable evidence is surfaced as a warning.
- Legacy event fallback remains visible but is not integrity-verified.
- Post-run summaries are available only for completed or failed Missions.
- Replay and branching are deferred to Task 045.
