# ADR-037 - Bounded Native Core Runtime Ownership

Status: Implemented.

Desktop runtime authority is limited to an exact `std::process::Child` that the current native Desktop process started using the canonical development Core launcher. No PID, port owner, command line, process name, shell, or persisted recovery data grants stop authority. Existing `core_transport.rs` remains the only Core HTTP transport and preserves native-only authentication.

External Core, authentication-required Core, and a non-canonical service occupying the configured loopback port are fail-closed states: no duplicate launch and no stop action. The managed child is polled for bounded readiness and bounded shutdown only; no automatic start or restart exists. A subsequent Desktop process does not inherit ownership of a surviving child.
