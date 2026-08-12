# ADR-044: Canonical Core Port Ownership and Collision Recovery

Status: Accepted and validated

HOTFIX-DESKTOP-FINAL-004 removes the installed release dependency on the historical global Core port. Each explicit Core start reserves an OS-assigned loopback port using `TcpListener::bind((127.0.0.1, 0))`, stores that port in the owned runtime state, and passes only the bounded numeric value to the canonical packaged sidecar through `PROMETHEUS_CORE_PORT` (with the legacy Desktop key retained for compatibility).

Transport endpoint construction reads the owned runtime port, so readiness, command, mission and model requests use the same exact endpoint. A startup bind/readiness failure is retried at most three times within the same explicit Start operation; this is bounded collision recovery, not auto-restart. Stop and child exit clear the runtime endpoint. Host binding remains hard-coded to `127.0.0.1`; authentication, CSRF, sidecar identity, no-console logging and all existing authority boundaries remain intact.

The sidecar includes the canonical skill manifest resource required for frozen startup. The historical port collision smoke test occupies 8765 and verifies Core readiness on a different loopback port without adopting the dummy listener. Release version is 0.1.4; models remain external.
