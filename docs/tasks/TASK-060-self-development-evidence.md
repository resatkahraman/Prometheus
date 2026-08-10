# TASK-060 - Trusted Self-Development Evidence Resolution

Status: Completed and validated.
Baseline: `70f8eccb8843d30a653502c80ec760f3e41baf9e`

This task adds a read-only resolver for the three TASK-059 evidence kinds: experience episodes, benchmark runs and execution receipts. Episode and benchmark references use exact project-scoped store lookups. Receipt references use `<mission_id>/<receipt_id>` and the existing verified receipt store.

Resolved evidence exposes only bounded scalar facts. Canonical SHA-256 digests bind source content, evidence references and the proposal digest without copying raw goals, details, paths, stdout or stderr. Missing sources, malformed records, digest mismatches and receipt corruption fail closed. No candidate, benchmark, approval, patch or execution behavior is included.

## Final validation

- Targeted TASK-060 evidence suite: `4 passed`.
- Focused regression: `14 passed, 1 warning`.
- Final full suite: `911 passed, 1 warning`.
- Warning: existing `StarletteDeprecationWarning` for the httpx/TestClient combination; it is not caused by TASK-060.
- The final full suite initially exposed an unrelated baseline Project Run history workspace-normalization bug, fixed separately on main before the successful final run.
