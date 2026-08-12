# DESKTOP-007: Native OS Integration

Status: Completed and validated.

Implemented capabilities:

- Coarse application/platform information without environment variables or device identifiers.
- Exact-path reveal after explicit single-file or single-folder selection.
- Text clipboard read/write with a 64 KiB UTF-8 payload limit and no polling/history.
- Bounded application-owned native notifications.
- Credential-free HTTPS browser handoff with dangerous schemes rejected.
- Truthful capability inventory and Turkish/English Settings UI.
- Structured bounded native errors.

General safe-open is intentionally unavailable because revealing an explicitly selected target meets the current need without introducing default-handler executable risk. No generic native dispatcher, shell, process launch, screen capture, input automation or direct model authority exists.

Validation:

- Targeted Rust/native: `9 passed`.
- Focused Desktop/Core/workspace regression: `32 passed, 1 warning`.
- Frontend: `npm ci` installed 73 packages with 0 vulnerabilities; production build passed.
- Rust/Tauri: `cargo test` passed 15 tests; `cargo check` passed.
- Static/security guards and `git diff --check`: passed.
- Full Python suite: `975 passed, 1 warning`.
- Warning: pre-existing Starlette/httpx TestClient deprecation warning.

Next stage: DESKTOP-008 - Packaging, Polish and Release.
