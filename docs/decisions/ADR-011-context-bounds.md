# ADR-011 — Deterministic Context Bounds

Status: Accepted and completed

All model-bound Prometheus context is subject to deterministic hard character ceilings after every source layer and wrapper is assembled. Required task evidence has priority over supplementary memory, and context remains bound to the Project Workspace snapshot captured at session or command creation.

Existing per-source limits are insufficient because wrappers, separators, Project DNA, Decision Memory and tool receipts also consume model input. Final assembly therefore applies one explicit ceiling. No model-based summarization is introduced. Compiler off, shadow and active modes all remain subject to the final bound and preserve their existing eligibility semantics.

## Validation

- Targeted: `7 passed`.
- Narrow compatibility regression: `2 passed, 1 warning`.
- Focused regression: `132 passed, 1 warning`.
- Full suite: `814 passed, 1 warning`.
- The warning is the pre-existing Starlette/httpx TestClient deprecation warning and is unrelated to TASK-051.
