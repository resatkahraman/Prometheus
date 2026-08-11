# ADR-026 - Canonical Approved Candidate Safe Patch Binding

Status: Accepted

TASK-066 closes the substitution gap between the approved canonical self-development chain and the exact approved Safe Patch artifact. Project/workspace equality is insufficient because multiple candidate changes may exist in the same project and workspace.

The relationship is explicit and digest-bound. TASK-066 validates both the promotion-authority chain and the Safe Patch plan/approval chain, then freezes their exact relationship in one deterministic immutable artifact. It performs no source mutation; TASK-067 may execute only the exact patch identity bound here.

Candidate approval is not arbitrary patch authorization, Safe Patch approval is not self-development candidate binding, and binding is not execution.

Validation: targeted 2 passed; focused 59 passed; full 928 passed, 1 warning. The warning is the pre-existing Starlette/httpx TestClient deprecation warning.
