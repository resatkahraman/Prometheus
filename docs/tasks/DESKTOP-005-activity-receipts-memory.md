# DESKTOP-005 - Activity, Receipts and Memory

Status: Implementation complete and automated validation passed; manual acceptance deferred.

DESKTOP-005 extends the native mission surface with read-only, exact-mission views over the canonical Mission Event Journal, immutable Execution Receipts, Mission History/Post-Run Summary and project-scoped Decision Memory. The Desktop delegates reads to Prometheus Core and does not append events, create or edit receipts, write memory, recompute digests, generate summaries, read local files or perform Git operations.

Activity uses canonical sequence ordering with bounded history. Receipts preserve canonical identities, outcomes and digests and expose unavailable/integrity states truthfully. Memory uses the existing project/workspace retrieval semantics and displays stored decisions only. Responses remain generation-bound to the selected mission, and terminal mission polling stops through the existing mission lifecycle behavior. Turkish and English strings are provided without adding dependencies.

Validation: targeted Desktop tests `27 passed`; focused canonical regression `133 passed, 1 warning`; Rust tests `4 passed`; `cargo check` passed; `npm.cmd ci` installed 73 packages with 0 vulnerabilities; frontend build passed; final full suite `970 passed, 1 warning`. Warning: existing Starlette/httpx TestClient deprecation warning. Manual acceptance remains deferred.
