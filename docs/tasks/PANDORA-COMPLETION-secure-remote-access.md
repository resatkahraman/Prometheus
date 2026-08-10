# Pandora Completion - Secure Remote Access Hardening

Status: Completed
Branch: pandora-completion
Baseline: add78d57b0519021e48563ee02be2acfe0288097
Revision: `pandora-secure-remote-access-v1`

## Scope

This step adds a strict `http_remote_access_mode` profile. `direct` remains the default and preserves legacy behavior. `tailscale_serve` requires enabled remote access, the existing strong HTTP auth token, an ASCII allowlisted Tailscale login and one canonical HTTPS external origin.

The strict application gate accepts only a loopback backend peer plus the exact `Tailscale-User-Login` and external Host/origin. It does not trust forwarded client IP/proto headers. Verified Serve traffic still requires normal HTTP authentication for generic APIs and Pandora pairing/session security. Pairing-code generation is direct-local only; Pandora pair may traverse verified Serve and receives a Secure cookie.

## Operator topology

1. Prometheus origin listens on `127.0.0.1`.
2. Desktop and Pandora phone belong to the intended private Tailscale tailnet.
3. Tailscale Serve proxies the local Prometheus port.
4. Strict `tailscale_serve` mode is configured with the expected Tailscale login and exact HTTPS Serve origin.
5. Pairing code is generated locally on the desktop.
6. Phone opens Pandora through the private Serve HTTPS URL.
7. Phone pairs using the locally generated code.

Tailscale is operator-owned external infrastructure; no CLI, SDK, Funnel, public bind or tunnel configuration is performed by Prometheus. Voice and TASK-060 remain deferred. Localhost is part of the trusted computing boundary.

## Final validation

- Targeted Secure Remote Access suite: `47 passed`.
- Focused remote/Pandora security regression: `69 passed`.
- Final full suite: `913 passed, 1 warning`.
- Warning: existing Starlette/httpx TestClient deprecation warning.

The strict profile requires `http_remote_access_enabled`, a strong existing HTTP auth token, an allowlisted `Tailscale-User-Login` and an exact HTTPS `http_remote_external_origin`. Legacy `direct` mode remains compatible. The loopback peer, exact Host/origin and identity gates block forged non-loopback access; forwarded client headers are not trusted. Generic HTTP authentication, Pandora sessions, CSRF and ownership remain authoritative. Pairing-code creation remains direct-local only, while verified Serve pairing receives a Secure cookie.

Two compatibility fixes were completed: the network helper tolerates partial runtime settings without `AttributeError`, and middleware defaults a missing runtime remote-access mode to `direct`. Canonical Settings validation and strict fail-closed behavior were not weakened.
