# ADR-027 - Canonical Promotion Execution Receipt and Replay Contract

Status: Accepted and validated

TASK-067 introduces dedicated durable canonical replay evidence for self-development promotion execution. The existing mission-oriented `ExecutionReceiptStore` is intentionally not overloaded because it has no TASK-066 binding-consumption contract.

A successful promotion execution consumes one exact TASK-066 binding and that consumption survives process restart. Corrupted replay evidence fails closed and is never interpreted as an unconsumed binding. TASK-067 performs no source mutation; TASK-068 will use this store before and after canonical SafePatchExecutor execution.

Receipt/replay evidence is not promotion execution, binding consumption is not Git/main integration, failed execution does not consume a binding, and successful execution must durably consume a binding.

Validation: 7 targeted tests passed; 48 focused tests passed with 1 warning; the final full suite passed 935 tests with 1 warning. Warning: pre-existing Starlette/httpx TestClient deprecation warning. Next stage: TASK-068 - Canonical Supervised Promotion Execution.
