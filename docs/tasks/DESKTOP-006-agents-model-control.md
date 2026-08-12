# DESKTOP-006: Agents and Model Control

Status: Completed and validated.

The Desktop now presents bounded canonical agent and model inventory, capability routing, configured context and truthful Ollama availability in Turkish and English. It does not fabricate benchmark data; absent telemetry is shown as no observations.

Canonical local stack:

- Primary generation: `gemma4:e4b-it-qat`
- Embedding/RAG: `embeddinggemma:300m-qat-q4_0`
- Structured output/tool routing recommendation: `ministral-3:3b`

Safety properties include embedding provenance, explicit incompatibility/rebuild reporting, loopback-only Ollama access, no automatic model downloads, no hidden reasoning persistence and no direct model-to-tool authority.

Validation:

- Targeted DESKTOP-006: `5 passed`.
- Focused regression: `36 passed`.
- Frontend: `npm ci` installed 73 packages with 0 vulnerabilities; production build passed.
- Rust/Tauri: `cargo test` passed 6 tests; `cargo check` passed.
- Full Python suite: `975 passed, 1 warning`.
- Warning: pre-existing Starlette/httpx TestClient deprecation warning.

Next stage: DESKTOP-007 - Native OS Integration.
