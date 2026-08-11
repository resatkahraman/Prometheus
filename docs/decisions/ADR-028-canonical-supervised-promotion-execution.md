# ADR-028 - Canonical Supervised Promotion Execution

Status: Accepted and validated

TASK-068 is the canonical supervised source-mutation boundary for self-development. Execution requires the exact TASK-065 promotion authority, exact TASK-066 approved-patch binding, exact Safe Patch plan and approval, and the exact change payload bound by that plan.

Before mutation, TASK-068 persists a durable immutable execution claim. A successful execution is then recorded using the TASK-067 durable promotion execution receipt. A success receipt means consumed and replay-blocked; a claim without a success receipt means recovery-required and also blocks re-execution. This prevents crash windows from silently allowing the same approved binding to mutate source twice.

All source mutation is delegated exclusively to `SafePatchExecutor`. TASK-068 performs no Git or main-branch integration. Authority is distinct from execution, an approved binding is distinct from execution, an execution claim is distinct from a successful execution receipt, and source promotion is distinct from Git/main integration.

Validation: targeted `2 passed`; focused `73 passed, 1 warning`; full `937 passed, 1 warning`. Warning: pre-existing Starlette/httpx TestClient deprecation warning.
