# HOTFIX-DESKTOP-FINAL-002: Persistent Window Drag + Command Submit Blockers

## Status

Complete and automated-validated.

## Root causes and fixes

- The first drag fix relied on the declarative region alone, which did not persist through the installed custom-titlebar hit-testing path. The dedicated surface now invokes the supported Tauri `startDragging()` API only for left-button presses; controls are not descendants of that handler.
- The composer previously returned early behind the Core-ready gate, making an unavailable Core look like a silent send failure. It now renders a bounded readiness/authentication explanation. Ready submissions retain the canonical typed native client, loopback URL, authentication and CSRF header.

## Validation

- Targeted hotfix suite: `15 passed`.
- Focused Desktop/security regression: `66 passed`.
- Direct transport contract: valid request accepted; missing CSRF rejected; invalid body rejected.
- `npm ci`: 73 packages, 0 vulnerabilities; production build passed.
- Rust: `16 passed`; `cargo check` passed.
- Full suite: `984 passed, 1 warning` (pre-existing Starlette/httpx TestClient deprecation warning).
- Release: `Prometheus_0.1.2_x64-setup.exe`, 2,693,298 bytes, SHA-256 `8CA65E713EBB018A5C8C26139ACB083B6D217B524E9D9228DC9C37C27B315C80`.
- Signing is `NotSigned`; updater is not configured.

No Pandora or TASK-073 work is included. Comprehensive manual acceptance remains the next stage.
