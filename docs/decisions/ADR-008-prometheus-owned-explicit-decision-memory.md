# ADR-008 — Prometheus-Owned Explicit Decision Memory

Status: Accepted

Decision Memory is separate from Project DNA. `.adam/decision_memory.json` is Prometheus-owned runtime state, and only explicit writes create canonical records. Supervisor answers are not persisted automatically; remembering requires explicit confirmation.

Supersession preserves immutable records. Matching uses exact decision keys only; fuzzy, vector and graph retrieval are excluded. Reads are side-effect-free. Writes are bounded, idempotent, optimistic-concurrency protected and atomic, with record and store hashes verified fail-closed.

The manager uses an in-process `RLock`; multi-process file locking is outside Task 047. Event Journal may carry bounded application metadata but never decision content. Project DNA is not mutated, ProjectMemoryStore is unchanged, and Pandora/UI are unchanged.

Delete, forget and edit APIs are not provided.
