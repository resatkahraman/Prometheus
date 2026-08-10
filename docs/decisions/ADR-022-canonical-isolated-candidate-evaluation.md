# ADR-022 - Canonical Isolated Candidate Evaluation

Status: Accepted

Canonical isolated candidate evaluation is an immutable deterministic project-bound artifact derived from a canonical TASK-061 candidate and bounded evaluation observations.

Observations are digest-bound claims, not human approval and not promotion authority. Outcomes aggregate in the order `fail > inconclusive > pass`; therefore `pass != promotion approval`.

TASK-062 performs no candidate execution and no side effects. `promotion_allowed` remains false, and isolated-run observations must later be bound to authoritative execution evidence/receipts before any supervised promotion decision.

Validation: targeted 4 passed; focused 16 passed; full 918 passed, 1 warning. The warning is the pre-existing Starlette/httpx TestClient deprecation warning.
