# ADR-042: HOTFIX-DESKTOP-FINAL-002 Persistent Drag and Submit

## Status

Accepted and validated.

## Decision

The custom titlebar keeps its dedicated Tauri drag region and adds a narrow typed `startDragging()` fallback on left-button presses from that non-interactive surface only. Search and window controls remain interactive; no body-wide drag or manual coordinate movement is introduced.

The command composer remains bound to the canonical authenticated loopback Core transport. When Core is not ready, submission reports the exact readiness/authentication reason instead of silently returning. When ready, the native transport sends the validated message to `/v1/desktop/command` with `X-Prometheus-CSRF: 1`; no auth or CSRF bypass is permitted.

## Release evidence

Version `0.1.2` was built as an unsigned NSIS artifact `Prometheus_0.1.2_x64-setup.exe`. SHA-256: `8CA65E713EBB018A5C8C26139ACB083B6D217B524E9D9228DC9C37C27B315C80`. Updater remains not configured. The no-console release and exact managed Core launcher boundaries from HOTFIX-DESKTOP-FINAL-001 remain preserved.
