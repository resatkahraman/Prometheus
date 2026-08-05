# ADR-003: Cooperative Mission Pause and Single-Resume Checkpoint Architecture

- **Status**: Accepted
- **Date**: 2026-08-05

## Context
Prometheus requires a resilient, persistent mechanism to pause running missions cleanly, record operational checkpoints, and resume execution without corrupting state or running duplicate tasks.

## Decision
1. Mission pause is cooperative: pause requests do not terminate or interrupt active tool executions. The runtime pauses only upon reaching the next safe boundary.
2. Checkpoint storage is append-only and immutable. Each record contains strict sequence numbers, SHA-256 state hashes, and checkpoint hash chaining.
3. Resumption is single-use for an active pause. Validating state hash compatibility and clearing active pause state under in-process locks prevents double resume.
4. Checkpoints belong to Prometheus. No third-party workflow engines, SQL migrations, or external services are added.

## Consequences
- Running operations finish cleanly before pause takes effect.
- Historical checkpoints are immutable records and cannot be modified or truncated.
- Manual checkpoints are non-resumable snapshot records.
- Distributed/multi-process locking is deferred to future tasks.
- Error classification and automated recovery are delegated to TASK-043.
