# HOTFIX-DESKTOP-FINAL-001: Windows Release Acceptance Blockers

## Status

Complete and automated-validated.

## Fixed blockers

- Custom titlebar dragging uses a dedicated `data-tauri-drag-region` surface; minimize, maximize and close controls remain outside that drag region.
- Release Tauri binaries use the Windows GUI subsystem.
- The exact managed `app.desktop_server` child remains the only Core launcher and applies Windows `CREATE_NO_WINDOW`; no shell or arbitrary executable authority exists.
- Desktop command submission retains loopback/authenticated transport and includes the canonical `X-Prometheus-CSRF: 1` header for state-changing requests.
- Core-not-ready behavior remains truthful and does not clear the composer optimistically; successful clearing still occurs only after the canonical request resolves.

## Validation and release

- Targeted hotfix tests: `19 passed`.
- Focused Desktop/security regression: `65 passed`.
- Frontend: `npm ci` installed 73 packages with 0 vulnerabilities; production build passed.
- Rust: `cargo test` reported `16 passed`; `cargo check` passed.
- Final full suite: `983 passed, 1 warning` (pre-existing Starlette/httpx TestClient deprecation warning).
- NSIS artifact: `Prometheus_0.1.1_x64-setup.exe`, 2,693,379 bytes.
- SHA-256: `874D0B3FDF231B30F036C733721DB152E3ABA31BCB2F31F4A3B127ED259EC7BD`.
- Signing: unsigned / `NotSigned`.
- Updater: not configured.

No Pandora or TASK-073 work is included. Installer execution and comprehensive manual acceptance continue as the next supervised stage.
