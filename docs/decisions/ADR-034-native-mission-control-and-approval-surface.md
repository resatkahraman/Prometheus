# ADR-034 - Native Mission Control and Approval Surface

Status: Implemented and automated validation passed; manual acceptance deferred.

DESKTOP-003 extends the native desktop as a presentation and control surface over canonical Prometheus Core mission state. Mission detail and activity are read from the existing Supervisor routes; approval and rejection remain delegated to the existing Supervisor authority with exact mission, task, approval ID and approval version binding.

The Rust transport reuses the DESKTOP-002 loopback-only client, fixed paths, bounded identifiers, existing authentication, no redirects, bounded timeouts and no automatic retry for mutating decisions. React receives only typed Tauri operations and never receives the native token or arbitrary URL/host/path controls.

The workbench displays canonical mission status, task progression, pending approval identity, recent activity and truthful decision/transport outcomes. Polling is bounded and generation-bound so stale mission responses cannot overwrite a newly selected mission. No local mission or approval authority, optimistic mutation, fabricated state or direct WebView networking is introduced.

Manual Desktop acceptance remains deferred until the complete Desktop task series is finished.

Validation recorded: targeted Python `12 passed`; focused Python `28 passed, 1 warning`; Rust unit tests `4 passed`; final full Python suite `955 passed, 1 warning`. The warning is the pre-existing Starlette/httpx TestClient deprecation warning.
