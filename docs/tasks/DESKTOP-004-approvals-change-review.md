# DESKTOP-004 - Approvals and Change Review

Status: Implementation complete and automated validation passed; manual acceptance deferred.

DESKTOP-004 extends the DESKTOP-003 native mission surface with a bounded, read-only review contract for the exact mission and approval identity. Review data is sourced from Prometheus Core's canonical approval preview and binding state; the Desktop does not create authority, compile patches, regenerate diffs, read repository files, execute changes, or perform Git operations.

The review surface conditionally presents approval context, affected files, operation metadata, canonical preview content and evidence. Large artifacts are bounded and explicitly marked truncated. Missing evidence remains unavailable rather than being inferred as success. Review state is generation-bound to the selected mission and approval, and stale approvals disable decisions. Existing exact approve/reject routes, no optimistic mutation and no mutating retry behavior remain unchanged.

Validation: targeted review tests `8 passed`; Desktop regression `20 passed`; focused approval/Supervisor regression `71 passed, 1 warning`; Rust tests `4 passed`; `cargo check` passed; `npm.cmd ci` installed 73 packages with 0 vulnerabilities; frontend build passed; final full suite `963 passed, 1 warning`. Warning: existing Starlette/httpx TestClient deprecation warning. Manual acceptance remains deferred.
