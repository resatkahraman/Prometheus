# ADR-024 - Canonical Explicit Human Decision Binding

Status: Accepted

TASK-064 binds an explicit human `approve` or `reject` decision to one exact canonical TASK-063 decision-gate artifact. No decision is inferred from evaluation or gate state, and only `review_required` gates are eligible.

Approve creates promotion eligibility but not mutation authority. Reject creates a canonical negative human decision and no promotion eligibility. Neither decision permits source or main mutation.

Human approval binding is not promotion execution, and promotion eligibility is not source mutation authority.

Validation: targeted 3 passed; focused 22 passed; full 924 passed, 1 warning. The warning is the pre-existing Starlette/httpx TestClient deprecation warning.
