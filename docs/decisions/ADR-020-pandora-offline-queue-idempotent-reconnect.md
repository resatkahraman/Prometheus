# ADR-020 - Pandora Offline Queue and Idempotent Reconnect

Status: Accepted / Completed

Pandora uses an explicit bounded browser outbox rather than generic background sync. Only chat and read-only Project Run preview are safe to preserve; commits, approvals, pairing, logout and all mutations are never automatically replayed. The service worker remains shell-only because authenticated API requests, cookies, tokens, CSRF values and user data must not enter Cache Storage.

Each queued intent carries a UUID request ID and exact user-authored payload. The server scopes idempotency to Pandora session digest, operation and request ID, fingerprints canonical JSON, remembers only successful results in bounded in-memory state, and returns the original successful response on replay. Same ID with different input or concurrent use fails closed with 409. Missing IDs preserve compatibility, malformed IDs are rejected, and revoked/expired sessions lose replay state.

Explicit logout clears the local outbox while passive session expiry preserves non-expired intent for a future authenticated pairing. Queue flushing is visible, FIFO and stops on authentication, rate-limit, server or network failure. Mobile approvals, Mission Control, voice, public tunneling and general background sync remain separate completion work.

Client request IDs are not authentication. Idempotency is scoped to the authenticated Pandora device session and operation; successful replay prevents duplicate work after connectivity ambiguity, while the same ID with different canonical input fails closed with 409. Legacy requests without request IDs retain their historical response schemas.

Validation:
- Targeted Pandora offline/reconnect suite: 20 passed.
- Focused Pandora regression: 31 passed.
- Final full suite: 909 passed with 1 existing Starlette/httpx TestClient deprecation warning.
