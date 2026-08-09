# TASK-049 - Pandora Offline Queue and Idempotent Reconnect

Status: Completed
Branch: pandora-completion
Baseline: 70f8eccb8843d30a653502c80ec760f3e41baf9e

Revision: `pandora-offline-queue-v1`.

TASK-049 adds a bounded authenticated Pandora outbox. Only explicit chat and read-only Project Run preview intents may be retained in browser `localStorage`; mutations, pairing, logout, approvals, writes, execution and future mutation endpoints are never queued. Queue entries contain only the exact user payload, a UUID request ID and creation time, with 20-item, 24-hour and 32 KiB limits. Explicit logout clears the queue; passive expiry preserves it.

The service worker remains shell-only and network-only for `/v1/`; no API request, cookie, token, CSRF value, response or conversation history is cached. Reconnect flushing is visible, FIFO and authenticated, and reuses the stored request ID. Offline chat is visibly pending and offline preview never fabricates a response or enables commit.

The server validates `X-Pandora-Request-ID` and fingerprints the operation plus canonical payload. Successful responses only are retained in bounded in-memory, per-session replay state. Same-session/same-operation/same-ID/same-payload replays without another model, preview or rate-limit consumption; different payloads and concurrent duplicates fail with 409. Missing IDs remain backward-compatible, malformed IDs return 400, and revocation/expiry removes replay state.

No public bind, tunnel, voice, approval, Mission Control, database, filesystem, Git, subprocess, model or dependency behavior is added. Existing Pandora authentication, CSRF, Project Run preview/commit and session security remain authoritative.

## Final contract and validation

Queueable operations are chat and Project Run preview only. Pairing-code creation, pairing, logout, Project Run commit, approval/rejection, pause/resume, retry, rollback and generic POST requests are never queued.

The client outbox uses `localStorage` key `prometheus.pandora.outbox.v1`, with 20 entries, 24-hour age, 32 KiB serialized size, UUID request IDs and FIFO replay. Explicit logout clears it; passive session expiry preserves it. No session token, cookie, pairing code or other authentication material is stored.

Idempotency uses `X-Pandora-Request-ID`, scoped to Pandora session, operation and request ID. Canonical operation/payload JSON is SHA-256 fingerprinted. Successful responses only are cached; same input safely replays, different input returns 409, and live duplicates return 409. Replay state is bounded to 64 entries per session with a 24-hour TTL and is removed on revocation.

Requests without `X-Pandora-Request-ID` retain the legacy response shape. With a valid ID, the first successful response has `idempotent_replay = false` and a successful replay has `idempotent_replay = true`.

The service worker remains `pandora-shell-v5`, shell/static-only and network-only for `/v1/`; Background Sync, IndexedDB and API request caching are not used.

Validation: Targeted `20 passed`; Focused `31 passed`; Full `909 passed, 1 existing warning` (existing Starlette/httpx TestClient deprecation warning).
