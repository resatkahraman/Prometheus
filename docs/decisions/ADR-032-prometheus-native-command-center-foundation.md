# ADR-032 - Prometheus Native Command Center Foundation

Status: Accepted and validated

Prometheus Desktop is a distinct native product surface. Tauri 2 is the native shell and React/TypeScript is the presentation layer; Prometheus Python Core remains canonical authority. The webview receives no filesystem, shell, process, Git, patch-execution, credential or arbitrary remote-network authority.

DESKTOP-001 exposes only the narrowly permissioned `desktop_bootstrap` command and honest disconnected/preview states. Its foundation includes the custom Windows title bar, Activity Rail, contextual sidebar, workbench, responsive inspector, status bar and global Ctrl+K Command Center. The graphite/ember visual direction is approved and should be preserved while future work refines detail.

The frontend root is physically isolated from `src-tauri`, preventing the Vite watcher from traversing Cargo-generated Windows binaries. The generated application icon set is canonical, and Turkish/English UI uses persisted non-sensitive language preference with UTF-8-safe source text.

Validation completed: npm dependency installation passed with 73 packages and 0 vulnerabilities; the TypeScript/Vite production build, Rust/Tauri `cargo check`, icon generation (`icon.ico`), native launch and native visual QA all passed. Turkish/English UI passed review. Prometheus Core live transport is not yet connected; this is the native command-center foundation.

Next: DESKTOP-PKG-001 - Windows Development Packaging, to produce a normal installable/launchable Windows application for daily use without starting it from a terminal. DESKTOP-002 follows for Secure Core Transport and Live Command Surface.
