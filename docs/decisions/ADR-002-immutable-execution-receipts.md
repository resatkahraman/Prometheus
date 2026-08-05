# ADR-002: Immutable Execution Receipts

- **Status**: Accepted
- **Context**: Tools, workers, and verifications require individual execution auditability prior to terminal success.
- **Decision**: Every real terminal execution produces a Prometheus-owned immutable, hash-chained receipt before terminal success is recorded.
- **Consequences**: Secret sanitization, bounded previews, store-before-event sequence, and HTTP 409 corruption handling.
