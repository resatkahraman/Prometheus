# Pandora Completion - Mobile Approvals and Mission Control

Status: Completed
Branch: pandora-completion
Baseline: ca0c44fc17ae5ad6d690a6823010dff6f120548a

Revision: `pandora-mobile-mission-control-v1`.

This completion step enables only session-owned Project Run Mission Control: bounded read state, current approval/rejection, pause and resume through canonical Supervisor services. It uses a per-manager HMAC control secret and stateless token binding to the Pandora session, command and current approval identity. Raw approval IDs, versions, task IDs, arguments, previews, provider/model data and absolute paths are never projected.

All mutation routes require Pandora authentication, ownership, CSRF and per-session serialization. They are online-only, never enter the TASK-049 outbox and never retry automatically; ambiguous responses require a manual Mission Control refresh. Existing Supervisor approval ordering, checkpoint, pause/resume, history, recovery and execution semantics remain authoritative.

Retry, rollback, revert, recovery, archive, branch activation, decision-memory writes, SafePatch execution, terminal/tools, generic Supervisor commands, voice, tunnels and TASK-060 remain out of scope.

## Completed security contract

Mission Control is restricted to Project Runs owned by the current Pandora session. Supported controls are approve/reject of the current owned approval, pause/resume of the owned Project Run, and refresh/read of safe Mission Control state. Generic Supervisor administration remains unavailable; foreign commands return sanitized 404 responses and admin credentials do not bypass ownership.

Raw `approval_id`, `approval_version` and `task_id` are never exposed. The `pmc1_<64 lowercase hex>` HMAC-SHA256 token binds Pandora session, command ID, approval ID, approval version and the `pandora-mobile-mission-control-v1` revision. Its ephemeral server secret is not persisted; the token remains only in volatile JavaScript state and is not stored in local/session storage or URLs. A stale token cannot approve a subsequent queued approval.

Supervisor remains canonical for approval ordering, consumption, rejection, mission state, pause and resume. Pandora does not mutate approval records or duplicate checkpoint/recovery state machines. Approval, rejection, pause and resume are never queued or retried; ambiguous responses require Mission Control refresh.

Validation: 13 targeted passed; 32 focused passed; 910 full-suite passed with 1 existing Starlette/httpx TestClient deprecation warning.
