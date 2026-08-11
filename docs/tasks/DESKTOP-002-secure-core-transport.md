# DESKTOP-002 - Secure Core Transport and Live Command Surface

Status: Implementation complete; automated validation passed. Manual Desktop acceptance deferred until the complete Desktop task series is finished.

## Contract

- Python exposes a loopback-only `app.desktop_server` runner at `127.0.0.1`, default port `8765`.
- `PROMETHEUS_DESKTOP_CORE_PORT` is the only override and accepts integers from 1024 through 65535.
- `POST /v1/desktop/command` accepts a trimmed 1-20,000 character message and delegates to the canonical Supervisor ingress.
- `GET /v1/health` is reused for normalized native Core status.
- Rust owns all HTTP transport through a bounded `reqwest` client; the WebView never fetches Core directly.
- Redirects are disabled, timeouts are bounded and response bodies are capped at 1 MiB.
- Optional native `HTTP_AUTH_TOKEN` forwarding never reaches the WebView.
- Desktop command submission is not retried automatically after an uncertain transport failure.
- Tauri permissions are explicit for `desktop_bootstrap`, `desktop_core_status` and `desktop_submit_command`; no generic HTTP, filesystem, shell or process permission is added.

## User validation

Run the user-controlled Python dependency installation, targeted pytest, Rust checks/tests, frontend build and native loopback command test. The Core process must be started separately with `python -m app.desktop_server`; DESKTOP-002 does not grant the WebView process-start authority.

## Lifecycle boundary and next

Desktop native transport can communicate with a loopback Core. Core process auto-start and packaged sidecar lifecycle are not part of DESKTOP-002. A bounded runtime lifecycle step should precede broader Projects/Missions UX where required by the roadmap.

## Automated validation

- Targeted Python: `6 passed`.
- Focused Python regression (`tests/test_http_authentication.py`, `tests/test_http_local_access_guard.py`, `tests/test_supervisor_service.py`): `28 passed, 1 warning`.
- Rust unit tests: `3 passed`.
- Rust `cargo check`: passed.
- Frontend `npm.cmd ci`: 73 packages installed, 0 vulnerabilities.
- Frontend `npm.cmd run build`: passed.
- Final Python suite: `949 passed, 1 warning`.
- Warning: pre-existing Starlette/httpx TestClient deprecation warning.
- Static direct-network, retry, secret and mojibake guards passed; `git diff --check` passed.
- Manual Desktop acceptance is deferred until the complete Desktop task series is finished.
