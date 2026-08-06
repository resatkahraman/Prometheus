# ADR-007 — Repository-Owned Project DNA

Status: Accepted

## Decision

- Project DNA is a human-managed `PROJECT_DNA.json` file at the selected project root.
- The repository file is the sole source of truth.
- Project DNA is versioned with optimistic concurrency and idempotent updates.
- Writes are explicit, authenticated, CSRF-protected, bounded and atomic.
- Project DNA is read-only for agents, planners and Supervisor workers.
- Reads and writes perform no model, provider, tool, Mission or usage operation.
- Unsafe, secret-bearing, malformed, oversized and unsupported documents fail closed.
- Project DNA is root-scoped in Task 046; hierarchical overrides are not implemented.
- Project Memory remains learned runtime metadata and does not persist Project DNA content.
- Decision Memory remains a separate Task 047 capability.
- Skill manifests remain a separate Task 048 capability.
