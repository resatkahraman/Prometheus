use serde::Serialize;
use std::{collections::HashSet, path::{Component, Path, PathBuf}, sync::Mutex};
use tauri::AppHandle;
use tauri_plugin_clipboard_manager::ClipboardExt;
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_opener::OpenerExt;
use url::Url;

const MAX_CLIPBOARD_BYTES: usize = 64 * 1024;
const MAX_NOTIFICATION_TITLE_CHARS: usize = 128;
const MAX_NOTIFICATION_BODY_CHARS: usize = 1024;
const MAX_URL_CHARS: usize = 2048;
const CORE_RUNTIME_REQUIREMENT: &str = "development_workspace_python";
const UPDATER_STATE: &str = "not_configured";
const CODE_SIGNING_STATE: &str = "not_configured";

#[derive(Default)]
pub struct NativeOsState { grants: Mutex<HashSet<PathBuf>> }

#[derive(Debug, Serialize, Clone, PartialEq, Eq)]
pub struct NativeOsError { pub code: &'static str, pub message: &'static str }
impl NativeOsError { fn new(code: &'static str, message: &'static str) -> Self { Self { code, message } } fn operation_failed() -> Self { Self::new("operation_failed", "Native operation failed.") } }

#[derive(Serialize)]
pub struct NativeCapability { pub capability_id: &'static str, pub available: bool, pub platform: &'static str, pub requires_user_gesture: bool }
#[derive(Serialize)]
pub struct NativeEnvironmentInfo { pub os_family: &'static str, pub architecture: &'static str, pub application_version: String, pub runtime_platform: &'static str, pub core_runtime_requirement: &'static str, pub updater_state: &'static str, pub code_signing_state: &'static str }

fn canonical_existing(path: &Path) -> Result<PathBuf, NativeOsError> { path.canonicalize().map_err(|_| NativeOsError::new("path_not_found", "Selected path is unavailable.")) }
fn grant_selected(state: &NativeOsState, path: PathBuf) -> Result<String, NativeOsError> { let canonical = canonical_existing(&path)?; state.grants.lock().map_err(|_| NativeOsError::operation_failed())?.insert(canonical.clone()); canonical.into_os_string().into_string().map_err(|_| NativeOsError::new("invalid_request", "Selected path cannot be represented safely.")) }
fn validate_granted(state: &NativeOsState, submitted: &str) -> Result<PathBuf, NativeOsError> { if submitted.is_empty() || submitted.len() > 32_768 { return Err(NativeOsError::new("invalid_request", "Path request is invalid.")); } let submitted_path = Path::new(submitted); if !submitted_path.is_absolute() || submitted_path.components().any(|part| matches!(part, Component::ParentDir | Component::CurDir)) { return Err(NativeOsError::new("invalid_request", "Path request is not canonical.")); } let canonical = canonical_existing(submitted_path)?; let grants = state.grants.lock().map_err(|_| NativeOsError::operation_failed())?; if !grants.contains(&canonical) { return Err(NativeOsError::new("outside_allowed_scope", "Path is outside the explicitly selected scope.")); } Ok(canonical) }
fn validate_url(raw: &str) -> Result<Url, NativeOsError> { if raw.is_empty() || raw.len() > MAX_URL_CHARS { return Err(NativeOsError::new("invalid_url", "External URL is invalid.")); } let parsed = Url::parse(raw).map_err(|_| NativeOsError::new("invalid_url", "External URL is invalid."))?; if parsed.scheme() != "https" || !parsed.username().is_empty() || parsed.password().is_some() || parsed.host_str().is_none() { return Err(NativeOsError::new("invalid_url", "Only public HTTPS URLs without credentials are allowed.")); } Ok(parsed) }
fn validate_notification(title: &str, body: &str) -> Result<(), NativeOsError> { if title.trim().is_empty() || title.chars().count() > MAX_NOTIFICATION_TITLE_CHARS || body.chars().count() > MAX_NOTIFICATION_BODY_CHARS { return Err(NativeOsError::new("payload_too_large", "Notification content is invalid or too large.")); } Ok(()) }

pub fn environment(app: &AppHandle) -> NativeEnvironmentInfo { NativeEnvironmentInfo { os_family: std::env::consts::FAMILY, architecture: std::env::consts::ARCH, application_version: app.package_info().version.to_string(), runtime_platform: std::env::consts::OS, core_runtime_requirement: CORE_RUNTIME_REQUIREMENT, updater_state: UPDATER_STATE, code_signing_state: CODE_SIGNING_STATE } }
pub fn capabilities() -> Vec<NativeCapability> { let platform = std::env::consts::OS; [("app_info", true, false), ("reveal_path", cfg!(desktop), true), ("open_path", false, true), ("clipboard_read", true, true), ("clipboard_write", true, true), ("notification", cfg!(desktop), true), ("select_file", cfg!(desktop), true), ("select_folder", cfg!(desktop), true), ("open_external_url", cfg!(desktop), true)].into_iter().map(|(capability_id, available, requires_user_gesture)| NativeCapability { capability_id, available, platform, requires_user_gesture }).collect() }
pub fn select_file(app: &AppHandle, state: &NativeOsState) -> Result<Option<String>, NativeOsError> { app.dialog().file().blocking_pick_file().map(|value| value.into_path().map_err(|_| NativeOsError::new("invalid_request", "Selected file is invalid.")).and_then(|path| grant_selected(state, path))).transpose() }
pub fn select_folder(app: &AppHandle, state: &NativeOsState) -> Result<Option<String>, NativeOsError> { app.dialog().file().blocking_pick_folder().map(|value| value.into_path().map_err(|_| NativeOsError::new("invalid_request", "Selected folder is invalid.")).and_then(|path| grant_selected(state, path))).transpose() }
pub fn reveal_path(app: &AppHandle, state: &NativeOsState, path: &str) -> Result<(), NativeOsError> { let path = validate_granted(state, path)?; app.opener().reveal_item_in_dir(path).map_err(|_| NativeOsError::operation_failed()) }
pub fn read_clipboard(app: &AppHandle) -> Result<String, NativeOsError> { let text = app.clipboard().read_text().map_err(|_| NativeOsError::operation_failed())?; if text.len() > MAX_CLIPBOARD_BYTES { return Err(NativeOsError::new("payload_too_large", "Clipboard text exceeds the safe limit.")); } Ok(text) }
pub fn write_clipboard(app: &AppHandle, text: String) -> Result<(), NativeOsError> { if text.len() > MAX_CLIPBOARD_BYTES { return Err(NativeOsError::new("payload_too_large", "Clipboard text exceeds the safe limit.")); } app.clipboard().write_text(text).map_err(|_| NativeOsError::operation_failed()) }
pub fn notify(app: &AppHandle, title: String, body: String) -> Result<(), NativeOsError> { validate_notification(&title, &body)?; app.notification().builder().title(title).body(body).show().map_err(|_| NativeOsError::operation_failed()) }
pub fn open_external_url(app: &AppHandle, raw: String) -> Result<(), NativeOsError> { let url = validate_url(&raw)?; app.opener().open_url(url.as_str(), None::<&str>).map_err(|_| NativeOsError::operation_failed()) }

#[cfg(test)] mod tests { use super::*;
#[test] fn accepts_public_https() { assert!(validate_url("https://example.com/docs").is_ok()); }
#[test] fn rejects_dangerous_schemes() { for value in ["javascript:alert(1)", "file:///C:/secret", "data:text/plain,x", "http://example.com"] { assert_eq!(validate_url(value).unwrap_err().code, "invalid_url"); } }
#[test] fn rejects_url_credentials() { assert_eq!(validate_url("https://user:pass@example.com").unwrap_err().code, "invalid_url"); }
#[test] fn bounds_notification_content() { assert!(validate_notification("Prometheus", "Ready").is_ok()); assert_eq!(validate_notification("", "body").unwrap_err().code, "payload_too_large"); assert_eq!(validate_notification("title", &"x".repeat(1025)).unwrap_err().code, "payload_too_large"); }
#[test] fn clipboard_limit_is_64_kib() { assert_eq!(MAX_CLIPBOARD_BYTES, 65_536); }
#[test] fn release_states_are_truthful() { assert_eq!(CORE_RUNTIME_REQUIREMENT, "development_workspace_python"); assert_eq!(UPDATER_STATE, "not_configured"); assert_eq!(CODE_SIGNING_STATE, "not_configured"); }
#[test] fn ungranted_paths_fail_closed() { let state = NativeOsState::default(); let error = validate_granted(&state, env!("CARGO_MANIFEST_DIR")).unwrap_err(); assert_eq!(error.code, "outside_allowed_scope"); }
#[test] fn traversal_is_rejected_before_resolution() { let state = NativeOsState::default(); let submitted = format!("{}\\src\\..", env!("CARGO_MANIFEST_DIR")); assert_eq!(validate_granted(&state, &submitted).unwrap_err().code, "invalid_request"); }
#[test] fn selected_exact_path_is_allowed() { let state = NativeOsState::default(); let canonical = canonical_existing(Path::new(env!("CARGO_MANIFEST_DIR"))).unwrap(); state.grants.lock().unwrap().insert(canonical.clone()); assert_eq!(validate_granted(&state, canonical.to_str().unwrap()).unwrap(), canonical); }
#[test] fn open_path_is_intentionally_unavailable() { assert!(!capabilities().into_iter().find(|item| item.capability_id == "open_path").unwrap().available); }
}
