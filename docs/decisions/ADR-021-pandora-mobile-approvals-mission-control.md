# ADR-021 - Pandora Mobile Approvals and Mission Control

Status: Accepted / Completed

Pandora Mission Control is a bounded security/projection wrapper over existing Supervisor services. A device may control only Project Runs registered to its own live Pandora session; generic Supervisor administration remains forbidden and foreign commands are hidden as 404.

The client receives no raw approval identifiers, versions or task IDs. A stateless HMAC-SHA256 control token binds the session, command, current approval and version, so a stale token cannot approve a later queue item. Supervisor remains the approval authority, and canonical pause/resume services remain the mission lifecycle authority. Approval, rejection, pause and resume are never placed in the offline outbox; ambiguous responses require Mission Control refresh/reconciliation.

Retry, rollback, recovery, revert, archive, branching, direct SafePatch execution, voice, public bind and mobile approval beyond this scoped Project Run surface remain deferred. Mission Control is a safe projection, not raw mission history.

Pandora is not a generic Supervisor administration client. Only Project Runs created by the same Pandora session may be controlled, and raw Supervisor approval identity is never sent to the phone. The stateless HMAC token binds session, command, approval, approval version and revision; Supervisor remains authoritative for ordering, consumption, idempotency and rejection. Canonical mission pause/resume APIs are reused.

Mobile mutations are intentionally excluded from the offline outbox. Network ambiguity is reconciled by refreshing server state rather than replaying mutations. Retry, rollback, revert, recover, archive, branch activation, SafePatch direct execution and terminal remain unavailable on Pandora.

Validation:
- Targeted Mission Control suite: 13 passed.
- Focused Pandora regression: 32 passed.
- Final full suite: 910 passed with 1 existing Starlette/httpx TestClient deprecation warning.
