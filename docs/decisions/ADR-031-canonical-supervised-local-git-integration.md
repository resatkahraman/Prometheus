# ADR-031 - Canonical Supervised Local Git Integration

Status: Accepted and validated

TASK-071 is the canonical supervised LOCAL Git integration execution boundary. It requires valid TASK-069 verification and fresh TASK-070 human approval, independently revalidates postimages and exact Git-visible paths, persists a claim before mutation, stages only approved paths, creates one promotion commit, and advances local `main` only with `merge --ff-only`.

No reset, force, rebase, history rewrite or remote operation is permitted. A claim without a success receipt is recovery-required. Remote publication is outside TASK-071.

Validation: targeted `1 passed`; focused `40 passed, 1 warning`; full `943 passed, 1 warning`. Warning: pre-existing Starlette/httpx TestClient deprecation warning. The local self-development promotion chain TASK-059 -> TASK-071 is complete; remote publication automation is not implemented.
