# ADR-020 - Trusted Self-Development Evidence Resolution

Status: Accepted

Prometheus-owned authoritative stores are the only accepted evidence sources. Evidence is resolved read-only and fail-closed. Proposal evidence digests bind canonical, secret-safe projections of source evidence; raw evidence content is not copied into resolved snapshots.

Experience episodes and benchmark runs are project-scoped through exact SQL lookups. Execution receipts retain the existing immutable hash-chain authority and use the canonical `<mission_id>/<receipt_id>` reference syntax. Current receipt records are mission-bound; no additional project identity was invented for historical receipts.

TASK-060 does not materialize candidates, evaluate them, request approval, promote, or execute patches.

Validation: targeted 4 passed; focused 14 passed, 1 warning; full 911 passed, 1 warning. The warning is the pre-existing Starlette/httpx TestClient deprecation warning. An unrelated baseline Project Run history workspace-normalization bug was fixed separately on main before the successful final suite.
