# ADR-001: Canonical Mission Event Journal

- **Status**: Accepted
- **Context**: Supervisor event history required an immutable, tamper-evident audit record.
- **Decision**: Mission history is a Prometheus-owned append-only, strictly sequenced, SHA-256 hash-chained JSONL journal.
- **Consequences**: Fail-closed integrity check on corruption, legacy backward compatibility fallback, zero-side-effect read endpoints.
