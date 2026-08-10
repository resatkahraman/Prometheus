# ADR-025 - Canonical Supervised Promotion Authority

Status: Accepted

TASK-065 creates a canonical deterministic promotion-authority artifact only from an exact validated TASK-064 explicit human APPROVE decision. A human REJECT decision cannot produce promotion authority.

Promotion authority proves that the canonical chain may advance to a future supervised promotion executor. It performs no promotion and grants no direct source or main mutation capability.

Explicit human approval binding is distinct from promotion authority; promotion authority is distinct from promotion execution, source mutation authority and main mutation authority. TASK-065 is stateless and does not track authority consumption; future execution/receipt layers must enforce replay/idempotency rules.
