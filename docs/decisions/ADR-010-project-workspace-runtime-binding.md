# ADR-010 — Snapshot-Bound Project Workspaces

Status: Accepted

## Decision

The active project is a default for new work, not a mutable global execution target. Each Agent session and Supervisor command resolves and snapshots its workspace; an explicit workspace overrides the active selection and a missing selection falls back to the configured root.

Every runtime receives a distinct scoped ToolRegistry while sharing only the ApprovalManager. Shared Settings and process CWD are never mutated. Approval execution remains bound to the original session registry. Project DNA, Decision Memory, planner and workers use the same snapped project, and state is stored as relative paths with atomic persistence, bounded size, optimistic concurrency, idempotency and digest validation.

No Pandora/UI changes are part of TASK-050. Project Memory namespace isolation remains a later context-bound task if not already supported.
