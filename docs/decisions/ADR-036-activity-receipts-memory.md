# ADR-036 - Activity, Receipts and Decision Memory Read Boundary

Status: Implemented and automated validation passed; manual acceptance deferred.

Prometheus Core remains canonical for Mission Event Journal ordering, immutable Execution Receipts, Mission History/Post-Run Summary and Decision Memory. DESKTOP-005 exposes bounded native read operations bound to an exact mission and, for memory, the mission's canonical workspace scope.

The Desktop never recomputes receipt hashes, synthesizes receipts or events, edits historical records, writes Decision Memory, reads repository/log files, or generates an AI summary. Missing, corrupt or truncated evidence is rendered as unavailable or explicitly bounded. Existing approval authority and change review behavior remain unchanged. Manual acceptance is deferred until the complete Desktop task series is finished.

Validation: targeted Desktop tests `27 passed`; focused canonical regression `133 passed, 1 warning`; final full suite `970 passed, 1 warning`. The warning is the pre-existing Starlette/httpx TestClient deprecation warning.
