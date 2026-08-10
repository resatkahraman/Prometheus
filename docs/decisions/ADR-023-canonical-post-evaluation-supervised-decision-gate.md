# ADR-023 - Canonical Post-Evaluation Supervised Decision Gate

Status: Accepted

A canonical post-evaluation gate determines only whether a valid evaluated self-development candidate is eligible for explicit human review. The gate is immutable, deterministic, project-bound and digest-bound.

```text
pass -> review_required
fail -> blocked_failed
inconclusive -> blocked_inconclusive
```

Human review eligibility is not human approval. The gate creates no human approval and authorizes no promotion or mutation. It performs no execution and has no side effects.

Validation: targeted 3 passed; focused 19 passed; full 921 passed, 1 warning. The warning is the pre-existing Starlette/httpx TestClient deprecation warning.
