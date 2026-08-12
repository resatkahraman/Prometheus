# HOTFIX-DESKTOP-FINAL-004 - Canonical Core Port Ownership and Collision Recovery

Status: Completed and validated.

The installed Core runtime now negotiates an OS-assigned loopback port for every explicit Start. The selected numeric port is held in the owned native runtime state and passed only to the exact packaged sidecar through `PROMETHEUS_CORE_PORT`; Desktop transport reads the same state for readiness and all Core requests. The canonical host remains `127.0.0.1`, with existing authentication and CSRF unchanged.

Startup bind/readiness failure is bounded to three attempts in one explicit Start operation. It never scans port ranges, adopts an arbitrary listener, restarts a previously-ready child, or introduces arbitrary process authority. Stop and early child exit clear the endpoint. The frozen sidecar build now includes `config/skill_manifests.json`, allowing installed Core startup to initialize its integrity-checked manifest catalog.

Validation:

- Targeted Desktop/runtime tests: `22 passed`.
- Native Rust tests: `18 passed`.
- Occupied-default-port smoke: PASS; dummy listener held 8765, canonical Core reached READY on 18766 and was stopped cleanly.
- Non-repository sidecar smoke: PASS.
- `npm.cmd ci`: 73 packages, 0 vulnerabilities.
- Frontend build: PASS.
- `cargo test` and `cargo check`: PASS.
- Final full pytest: `991 passed, 1 warning` (existing Starlette/httpx TestClient deprecation warning).
- NSIS artifact: `Prometheus_0.1.4_x64-setup.exe`, 38,372,221 bytes, SHA-256 `66A4823D4ED75722DF5E1A3DFC92160D5CA805C89DB2F8E9E303684532CEA0E8`.
- Release: `0.1.4` NSIS, unsigned; updater not configured.
