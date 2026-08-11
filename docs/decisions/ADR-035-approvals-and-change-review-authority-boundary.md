# ADR-035 - Approvals and Change Review Authority Boundary

Status: Implemented and automated validation passed; manual acceptance deferred.

DESKTOP-004 keeps Prometheus Core as the sole approval and change authority. The native Desktop is a review/control surface bound exactly to `mission_id` and `approval_id`; it reuses canonical approval preview and evidence artifacts when available and never substitutes another approval or mission.

No repository source-read fallback or regenerated replacement diff is introduced. Review payloads are bounded and explicitly report truncation or unavailable artifacts. React renders all review data as escaped text with no raw HTML. Approve/reject continues to use the DESKTOP-003 canonical routes with exact identity binding, no optimistic mutation and no mutating auto retry. Manual acceptance remains deferred until the complete Desktop task series is finished.

Validation: targeted review tests `8 passed`; Desktop regression `20 passed`; focused approval/Supervisor regression `71 passed, 1 warning`; final full suite `963 passed, 1 warning`. The warning is the pre-existing Starlette/httpx TestClient deprecation warning.
