# HOTFIX-DESKTOP-FINAL-003 - Installed Release Core Runtime Binding

Status: Completed and validated.

This hotfix makes the installed Windows application capable of starting Prometheus Core without a repository checkout, current-directory assumptions, PATH scanning or user-supplied Python. Release builds generate and embed one canonical PyInstaller sidecar through Tauri `externalBin`; debug builds retain the existing workspace-managed Python workflow.

The runtime keeps the explicit DESKTOP-RUNTIME-001 lifecycle contract: one owned child, duplicate-start prevention, explicit stop, bounded readiness/stop timeouts, no shell or arbitrary process execution, no auto-start and no auto-restart. The sidecar uses loopback-only transport with existing authentication and CSRF requirements. Mutable runtime data uses application data storage; installed resources remain read-only. Ollama models remain external.

Validation recorded:

- Sidecar build: PASS; canonical executable generated and non-zero.
- Sidecar smoke: PASS from a temporary non-repository working directory; `/v1/health` reached ready and the process stopped cleanly.
- Targeted hotfix tests: `9 passed`.
- Rust tests: `17 passed`.
- `cargo check`: PASS.
- `npm.cmd ci`: `73 packages`, `0 vulnerabilities`.
- Frontend production build: PASS.
- NSIS build: PASS; `Prometheus_0.1.3_x64-setup.exe`.
- Artifact SHA-256: `A8A2DCFBCB26DB9CE85961CD5AE9D7786B1B897E6FB2AD758BAF915C437CBE82`.
- Artifact signature: `NotSigned`; signing and updater remain future release work.

The canonical model stack remains `gemma4:e4b-it-qat`, `embeddinggemma:300m-qat-q4_0` and `ministral-3:3b`; model files and secrets are not bundled.
