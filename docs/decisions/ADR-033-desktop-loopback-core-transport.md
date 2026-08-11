# ADR-033 - Desktop Loopback Core Transport

Status: Implemented and automated-validated. Manual Desktop acceptance is deferred until the complete Desktop task series is finished.

DESKTOP-002 connects the native desktop through a bounded Rust-owned transport. The WebView has no direct Core network access; Rust communicates only with `http://127.0.0.1:<validated-port>`. The default port is `8765`, with only the integer `PROMETHEUS_DESKTOP_CORE_PORT` override in the range 1024-65535. No arbitrary Core URL or host is accepted.

The native client follows no redirects, enforces bounded connect/overall timeouts and a 1 MiB response limit. An optional native-process `HTTP_AUTH_TOKEN` is forwarded as a Bearer credential only to the loopback Core; it is never returned to or persisted by the WebView.

Desktop commands use the dedicated `/v1/desktop/command` adapter, which delegates to the canonical Supervisor ingress. `/v1/orchestrate` is not the Desktop authority. The adapter remains loopback-only and preserves the existing global authentication middleware and Supervisor mission lifecycle. Command submission has no automatic retry after an uncertain transport failure.

The Tauri surface exposes only typed `desktop_bootstrap`, `desktop_core_status` and `desktop_submit_command` commands. Filesystem, shell, process and arbitrary network authority remain denied to the WebView.

Automated validation passed: 6 targeted Python tests, 28 focused regression tests, 3 Rust unit tests, Rust `cargo check`, frontend dependency installation/build and 949 full Python tests. The only warning is the pre-existing Starlette/httpx TestClient deprecation warning. DESKTOP-002 does not auto-start Prometheus Core; native packaged Core lifecycle remains a later bounded Desktop runtime concern.
