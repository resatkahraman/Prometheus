# ADR-022 - Pandora Secure Remote Access

Status: Accepted / Completed

Prometheus remains localhost-bound. Pandora v1 uses HTTPS Tailscale Serve inside the intended private tailnet as the approved remote topology; Tailscale Funnel, public sharing and public listeners are explicitly excluded. Tailscale identity is an additional transport gate, never a replacement for HTTP authentication, Pandora pairing/session, CSRF or Project Run ownership.

Strict `tailscale_serve` traffic requires a loopback immediate backend peer, exactly one allowlisted `Tailscale-User-Login`, and an exact configured HTTPS Host/origin. Forwarded client-IP/proto headers are never authorization inputs. Direct non-loopback traffic, duplicate security headers, wrong identity, wrong host and wrong Origin fail closed, protecting against an accidental `0.0.0.0` bind. Localhost remains inside the trusted computing boundary.

Pairing-code generation remains direct-local only; a verified Serve request may submit a locally generated code but does not bypass pairing. Cookies created through trusted TLS termination are Secure while retaining HttpOnly, SameSite and path policy. Generic application authentication remains authoritative. Security response headers are added only for verified Serve traffic.

The approved model is phone -> private Tailscale tailnet HTTPS -> Tailscale Serve -> localhost Prometheus origin -> FastAPI. Tailscale Funnel, public tunnels, anonymous URLs and router exposure are not supported. Strict Serve requests require loopback backend peer, exact allowlisted identity and exact external HTTPS Host/origin; cross-origin browser requests fail closed. Forwarded client-IP headers are not security authority, and localhost remains part of the trusted computing boundary.

Validation:
- Targeted Secure Remote Access suite: 47 passed.
- Focused remote/Pandora security regression: 69 passed.
- Final full suite: 913 passed with 1 existing Starlette/httpx TestClient deprecation warning.
