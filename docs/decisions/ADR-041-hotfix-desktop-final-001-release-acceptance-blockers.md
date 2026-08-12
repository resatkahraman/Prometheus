# ADR-041: HOTFIX-DESKTOP-FINAL-001 Release Acceptance Blockers

## Status

Accepted and validated.

## Decision

The Windows release candidate is version `0.1.1`. The custom titlebar owns a dedicated Tauri drag surface while window controls remain interactive. Release builds use the Windows GUI subsystem, and the exact bounded Python Core launcher applies `CREATE_NO_WINDOW` on Windows so neither the Desktop nor its managed child exposes an interactive console.

Desktop command submission remains loopback-only, authenticated and canonical. State-changing Core requests carry `X-Prometheus-CSRF: 1`; no auth bypass, arbitrary provider URL, shell authority, process generalization or model-stack change was introduced.

## Release evidence

`Prometheus_0.1.1_x64-setup.exe` was built as an unsigned NSIS artifact. Its SHA-256 is `874D0B3FDF231B30F036C733721DB152E3ABA31BCB2F31F4A3B127ED259EC7BD`. Updater infrastructure and production code signing remain unconfigured. Installer execution and comprehensive manual acceptance are deferred to `DESKTOP-FINAL-ACCEPTANCE`.
