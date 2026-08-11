# ADR-030 - Canonical Human Git Integration Approval

Status: Accepted

TASK-070 introduces a dedicated canonical durable human authorization for local Git/main integration. Existing `ApprovalManager`/`PendingAction` remains operational in-memory approval infrastructure and is not canonical self-development authority because it uses random in-memory tokens and does not bind an exact TASK-069 verification or Git baseline.

Promotion approval does not authorize Git integration. Post-promotion verification does not authorize Git integration. This immutable approval binds one exact verified source state, source branch, target `main`, and expected local main baseline SHA. Remote publication remains unauthorized.
