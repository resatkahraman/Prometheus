# ADR-006 — Checkpoint-Rooted Session Branching

Status: Accepted

## Decision

- A branch is a child Mission, never a mutation of its parent.
- The source checkpoint is the immutable authority.
- The parent journal remains unchanged.
- Child event and checkpoint evidence chains are independent.
- Private checkpoint snapshots are versioned.
- Lineage is held on child commands; no second lineage database exists.
- Branch creation is deterministic and idempotent.
- Creation is separate from explicit activation.
- Task 045 does not copy or rewind workspace files.
- Activation requires explicit shared-workspace acknowledgement.
- Historical model/tool calls are never replayed.
