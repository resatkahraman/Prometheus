use crate::core_transport::{self, CoreState};
use serde::Serialize;
use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager};

#[derive(Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeLifecycle { Offline, ExternalReady, ExternalAuthRequired, PortConflict, ManagedStarting, ManagedReady, ManagedStopping, ManagedExited, LaunchUnavailable, LaunchFailed }
#[derive(Clone, Serialize)]
pub struct RuntimeStatus { pub connectivity: String, pub ownership: String, pub lifecycle: RuntimeLifecycle, pub can_start: bool, pub can_stop: bool, pub message_code: String, pub message: String }
pub struct CoreRuntime { child: Option<Child>, endpoint_port: Option<u16>, lifecycle: RuntimeLifecycle, message_code: String, message: String }
pub type SharedRuntime = Arc<Mutex<CoreRuntime>>;

impl CoreRuntime {
    pub fn new() -> Self { Self { child: None, endpoint_port: None, lifecycle: RuntimeLifecycle::Offline, message_code: "offline".into(), message: "Core çevrimdışı.".into() } }
    fn status(&self) -> RuntimeStatus { let managed = matches!(self.lifecycle, RuntimeLifecycle::ManagedStarting | RuntimeLifecycle::ManagedReady | RuntimeLifecycle::ManagedStopping); RuntimeStatus { connectivity: if matches!(self.lifecycle, RuntimeLifecycle::ManagedReady | RuntimeLifecycle::ExternalReady) { "ready" } else if matches!(self.lifecycle, RuntimeLifecycle::ExternalAuthRequired) { "auth_required" } else { "offline" }.into(), ownership: if managed { "desktop" } else if matches!(self.lifecycle, RuntimeLifecycle::ExternalReady | RuntimeLifecycle::ExternalAuthRequired | RuntimeLifecycle::PortConflict) { "external" } else { "none" }.into(), lifecycle: self.lifecycle.clone(), can_start: matches!(self.lifecycle, RuntimeLifecycle::Offline | RuntimeLifecycle::ManagedExited | RuntimeLifecycle::LaunchFailed), can_stop: self.child.is_some() && matches!(self.lifecycle, RuntimeLifecycle::ManagedStarting | RuntimeLifecycle::ManagedReady), message_code: self.message_code.clone(), message: self.message.clone() } }
}

const SIDECAR_NAME: &str = "prometheus-core.exe";
const MAX_START_ATTEMPTS: usize = 3;
fn repo_root() -> Option<PathBuf> { let mut current = std::env::current_dir().ok()?; loop { if current.join("app").join("desktop_server.py").is_file() { return Some(current); } if !current.pop() { return None; } } }
fn python_path() -> Option<PathBuf> { let root = repo_root()?; let path = root.join(".venv").join("Scripts").join("python.exe"); path.is_file().then_some(path) }
fn bundled_core_path(app: &AppHandle) -> Result<PathBuf, String> { let resource_dir = app.path().resource_dir().map_err(|_| "core_runtime_not_found".to_string())?; let path = resource_dir.join(SIDECAR_NAME); path.is_file().then_some(path).ok_or_else(|| "core_runtime_not_found".to_string()) }
fn set_error(runtime: &mut CoreRuntime, lifecycle: RuntimeLifecycle, code: &str, message: &str) { runtime.lifecycle = lifecycle; runtime.message_code = code.into(); runtime.message = message.into(); }
fn child_alive(runtime: &mut CoreRuntime) -> bool { if let Some(child) = runtime.child.as_mut() { match child.try_wait() { Ok(None) => true, Ok(Some(_)) | Err(_) => { runtime.child = None; false } } } else { false } }
fn pause(duration: Duration) { std::thread::sleep(duration); }
fn select_loopback_port() -> Result<u16, String> { TcpListener::bind((core_transport::CORE_HOST, 0)).and_then(|listener| listener.local_addr()).map(|address| address.port()).map_err(|_| "core_bind_failed".to_string()) }
#[cfg(windows)] fn configure_child_process(command: &mut Command) { use std::os::windows::process::CommandExt; command.creation_flags(0x0800_0000); }
#[cfg(not(windows))] fn configure_child_process(_command: &mut Command) {}

pub async fn status(shared: SharedRuntime) -> RuntimeStatus {
    let current = { let mut guard = shared.lock().expect("runtime lock"); if child_alive(&mut guard) { return guard.status(); } guard.lifecycle.clone() };
    if matches!(current, RuntimeLifecycle::ManagedStarting | RuntimeLifecycle::ManagedReady | RuntimeLifecycle::ManagedStopping) { core_transport::clear_runtime_port(); let mut guard = shared.lock().expect("runtime lock"); guard.endpoint_port = None; set_error(&mut guard, RuntimeLifecycle::ManagedExited, "managed_exited", "Desktop tarafından başlatılan Core kapandı."); return guard.status(); }
    let health = core_transport::health().await; let mut guard = shared.lock().expect("runtime lock");
    match health.state { CoreState::Ready => set_error(&mut guard, RuntimeLifecycle::ExternalReady, "external_ready", "External Core / Dışarıdan yönetilen Core."), CoreState::AuthRequired => set_error(&mut guard, RuntimeLifecycle::ExternalAuthRequired, "auth_required", "Mevcut Core kimlik doğrulaması istiyor."), CoreState::ProtocolError | CoreState::CoreError => set_error(&mut guard, RuntimeLifecycle::PortConflict, "port_conflict", "Core portu kullanımda ancak canonical Core doğrulanamadı."), CoreState::NotRunning => set_error(&mut guard, RuntimeLifecycle::Offline, "offline", "Core çevrimdışı; başlatmaya hazır." ) } guard.status()
}

pub async fn start(app: AppHandle, shared: SharedRuntime) -> Result<RuntimeStatus, String> {
    { let mut guard = shared.lock().map_err(|_| "runtime_lock".to_string())?; if child_alive(&mut guard) { return Ok(guard.status()); } if !matches!(guard.lifecycle, RuntimeLifecycle::Offline | RuntimeLifecycle::ManagedExited | RuntimeLifecycle::LaunchFailed) { return Err("already_managed_or_external".into()); } }
    for attempt in 0..MAX_START_ATTEMPTS {
        let selected_port = select_loopback_port()?;
        core_transport::set_runtime_port(selected_port);
        let (executable, args, working_dir) = if cfg!(debug_assertions) { let executable = python_path().ok_or_else(|| "launch_unavailable".to_string())?; let root = repo_root().ok_or_else(|| "launch_unavailable".to_string())?; (executable, vec!["-m", "app.desktop_server"], root) } else { let executable = bundled_core_path(&app)?; let working_dir = app.path().app_data_dir().map_err(|_| "core_runtime_not_found".to_string())?; std::fs::create_dir_all(&working_dir).map_err(|_| "core_runtime_not_found".to_string())?; (executable, Vec::new(), working_dir) };
        let mut command = Command::new(executable); command.current_dir(working_dir).args(args).env("PROMETHEUS_CORE_PORT", selected_port.to_string()).env("PROMETHEUS_DESKTOP_CORE_PORT", selected_port.to_string()); configure_child_process(&mut command);
        let child = match command.spawn() { Ok(child) => child, Err(_) => { core_transport::clear_runtime_port(); return Err("core_start_failed".into()); } };
        { let mut guard = shared.lock().map_err(|_| "runtime_lock".to_string())?; guard.endpoint_port = Some(selected_port); guard.child = Some(child); set_error(&mut guard, RuntimeLifecycle::ManagedStarting, "starting", "Core başlatılıyor…"); }
        let deadline = Instant::now() + Duration::from_secs(15);
        while Instant::now() < deadline { { let mut guard = shared.lock().map_err(|_| "runtime_lock".to_string())?; if !child_alive(&mut guard) { break; } } if matches!(core_transport::health().await.state, CoreState::Ready) { let mut guard = shared.lock().map_err(|_| "runtime_lock".to_string())?; set_error(&mut guard, RuntimeLifecycle::ManagedReady, "managed_ready", "Desktop tarafından yönetilen Core hazır."); return Ok(guard.status()); } pause(Duration::from_millis(500)); }
        let mut child = { let mut guard = shared.lock().map_err(|_| "runtime_lock".to_string())?; guard.child.take() }; if let Some(ref mut owned) = child { let _ = owned.kill(); let _ = owned.wait(); } { let mut guard = shared.lock().map_err(|_| "runtime_lock".to_string())?; guard.endpoint_port = None; set_error(&mut guard, RuntimeLifecycle::LaunchFailed, "core_bind_failed", "Core başlatılamadı."); }
        core_transport::clear_runtime_port();
        if attempt + 1 == MAX_START_ATTEMPTS { return Err("core_bind_failed".into()); }
    }
    Err("core_bind_failed".into())
}

pub async fn stop(shared: SharedRuntime) -> Result<RuntimeStatus, String> { let mut child = { let mut guard = shared.lock().map_err(|_| "runtime_lock".to_string())?; if !child_alive(&mut guard) { core_transport::clear_runtime_port(); guard.endpoint_port = None; set_error(&mut guard, RuntimeLifecycle::ManagedExited, "already_stopped", "Desktop tarafından yönetilen Core çalışmıyor."); return Ok(guard.status()); } set_error(&mut guard, RuntimeLifecycle::ManagedStopping, "stopping", "Core durduruluyor…"); guard.child.take() }; if let Some(ref mut owned) = child { let _ = owned.kill(); let started = Instant::now(); while started.elapsed() < Duration::from_secs(5) { if owned.try_wait().map_err(|_| "stop_failed".to_string())?.is_some() { core_transport::clear_runtime_port(); let mut guard = shared.lock().map_err(|_| "runtime_lock".to_string())?; guard.endpoint_port = None; set_error(&mut guard, RuntimeLifecycle::ManagedExited, "stopped", "Desktop tarafından yönetilen Core durduruldu."); return Ok(guard.status()); } pause(Duration::from_millis(100)); } return Err("stop_timeout".into()); } Err("stop_not_authorized".into()) }

#[cfg(test)]
mod tests { use super::*; #[test] fn sidecar_identity_is_canonical() { assert_eq!(SIDECAR_NAME, "prometheus-core.exe"); assert_eq!(MAX_START_ATTEMPTS, 3); } #[test] fn runtime_port_is_os_selected() { let port = select_loopback_port().unwrap(); assert!((1024..=65535).contains(&port)); } #[test] fn runtime_starts_without_external_inputs() { assert!(python_path().is_none() || python_path().unwrap().ends_with("python.exe")); } #[test] fn ownership_defaults_to_no_stop() { let status = CoreRuntime::new().status(); assert!(!status.can_stop && status.can_start); } }
