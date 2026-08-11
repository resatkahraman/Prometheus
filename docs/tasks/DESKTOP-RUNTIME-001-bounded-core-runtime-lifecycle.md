# DESKTOP-RUNTIME-001 - Bounded Core Runtime Lifecycle

Status: Implemented and automated validation passed; manual acceptance deferred.

Prometheus Desktop may explicitly start the canonical development Core with the fixed `python -m app.desktop_server` entrypoint, repository working directory, loopback host `127.0.0.1`, and the same bounded native port resolver as `core_transport.rs`. The WebView supplies no executable, arguments, path, port, URL, token, PID, or process authority.

Only the exact native `Child` created by this Desktop process is owned. External, authentication-required, and unknown-port Core instances are never stopped. Start is explicit, duplicate starts are blocked natively, readiness is bounded to 15 seconds, and stop confirms the owned child exit within 5 seconds. There is no shell, auto-start, auto-restart, PID recovery, or port-owner/process discovery. After a Desktop crash, any surviving Core is external on the next launch. Packaging remains deferred; unavailable source launchers fail closed.

Validation: targeted Python `27 passed`; Rust unit tests `6 passed`; `cargo check` passed; `npm.cmd ci` installed 73 packages with 0 vulnerabilities; frontend build passed; final full Python suite `970 passed, 1 warning`. The warning is the pre-existing Starlette/httpx TestClient deprecation warning. Manual acceptance remains deferred until the complete Desktop series is finished.
