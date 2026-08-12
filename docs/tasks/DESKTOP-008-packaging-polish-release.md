# DESKTOP-008: Packaging, Polish and Release

## Status

Completed and automated-validated.

## Scope delivered

- Release identity remains Prometheus version `0.1.0` across Desktop package metadata, Tauri metadata and native diagnostics.
- The approved Windows icon resources are explicitly configured for the NSIS bundle.
- A Windows x86_64 NSIS release candidate was produced: `Prometheus_0.1.0_x64-setup.exe`.
- Artifact size: `2,691,188` bytes.
- SHA-256: `AE02EB3B5ED54F9E0DA8AB80241EB3CCE496F43982E88F8A05B681845EF3EDDF`.
- Windows code signing is not configured; the artifact is unsigned.
- Updater infrastructure is not configured.
- Local models and Ollama are not bundled and are never downloaded automatically.
- Release diagnostics truthfully report the workspace-managed Python Core runtime requirement, unsigned state and updater state.
- Native System UI now keeps long selected paths readable in constrained layouts and retains Turkish/English localization.

## Security and runtime boundary

The package is a release-candidate Desktop shell, not a standalone Python/Core bundle. It requires the canonical workspace-managed Python runtime and fails closed when that bounded runtime cannot be located. It does not discover arbitrary Python installations, auto-start Core, widen shell/process/filesystem authority, or weaken the existing CSP, model-routing or native-OS boundaries.

## Validation

- DESKTOP-008 targeted and affected Desktop tests: passed.
- Frontend dependency installation and production build: passed.
- Rust unit tests, `cargo check` and Tauri Windows/NSIS bundle build: passed.
- Static release/security checks and `git diff --check`: passed.
- Final Python suite: passed with the pre-existing Starlette/httpx TestClient deprecation warning.

## Deferred acceptance

Installer execution, installation behavior and complete user-facing end-to-end verification are deliberately deferred to `DESKTOP-FINAL-ACCEPTANCE - Comprehensive Manual End-to-End Acceptance Test`.
