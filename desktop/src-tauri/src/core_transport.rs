use reqwest::{redirect::Policy, Client, StatusCode};
use serde::{Deserialize, Serialize};
use std::env;
use std::time::Duration;
use std::sync::atomic::{AtomicU16, Ordering};

pub const CORE_HOST: &str = "127.0.0.1";
pub const DEFAULT_CORE_PORT: u16 = 8765;
static RUNTIME_PORT: AtomicU16 = AtomicU16::new(0);
const CSRF_HEADER_NAME: &str = "X-Prometheus-CSRF";
const CSRF_HEADER_VALUE: &str = "1";
const MAX_RESPONSE_BYTES: usize = 1024 * 1024;

#[derive(Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CoreState { NotRunning, Ready, AuthRequired, ProtocolError, CoreError }

#[derive(Clone, Serialize)]
pub struct CoreStatus { pub state: CoreState, pub code: String, pub message: String }

#[derive(Clone, Deserialize, Serialize)]
pub struct DesktopModelProfile { pub route_key: String, pub canonical_id: String, pub display_name: String, pub provider: String, pub local: bool, pub model_class: String, pub capabilities: Vec<String>, pub enabled: bool, pub configured: bool, pub availability: String, pub cost_class: String, pub configured_context_tokens: Option<u32> }
#[derive(Clone, Deserialize, Serialize)]
pub struct DesktopModelCatalog { pub models: Vec<DesktopModelProfile>, pub agents: Vec<serde_json::Value>, pub routing_information: String }

#[derive(Serialize)]
pub struct DesktopCommandRequest { pub message: String }

#[derive(Deserialize, Serialize)]
pub struct DesktopCommandResponse { pub status: String, pub mission_id: String, pub summary: Option<String>, pub requires_approval: bool }

#[derive(Clone, Deserialize, Serialize)]
pub struct MissionTaskView { pub id: String, pub title: String, pub status: String, pub assigned_agent: String, pub approval_id: Option<String>, pub approval_version: u32, pub approval_state: String, pub approval_description: Option<String>, pub approval_preview: Option<serde_json::Value>, pub approval_tool: Option<String>, pub last_approval_message: Option<String> }

#[derive(Clone, Deserialize, Serialize)]
pub struct MissionView { pub id: String, pub goal: String, pub status: String, pub tasks: Vec<MissionTaskView>, pub created_at: String, pub updated_at: Option<String>, pub operation_message: Option<String>, pub failure_reason: Option<String> }

#[derive(Clone, Deserialize, Serialize)]
pub struct MissionEventView { pub sequence: u64, pub event_type: String, pub message: String, pub occurred_at: String, pub task_id: Option<String>, pub approval_id: Option<String> }

#[derive(Clone, Deserialize, Serialize)]
pub struct MissionEventsView { pub mission_id: String, pub events: Vec<MissionEventView>, pub count: u64, pub has_more: bool }
#[derive(Clone, Deserialize, Serialize)]
pub struct MissionHistoryView { pub mission_id: String, pub command_status: String, pub terminal: bool, pub entries: Vec<serde_json::Value>, pub count: u64, pub after_sequence: u64, pub next_after_sequence: Option<u64>, pub has_more: bool, pub source: String, pub integrity_verified: bool, pub last_sequence: u64, pub last_event_hash: Option<String> }
#[derive(Clone, Deserialize, Serialize)]
pub struct ReceiptPageView { pub mission_id: String, pub receipts: Vec<serde_json::Value>, pub count: u64, pub after_sequence: u64, pub next_after_sequence: Option<u64>, pub has_more: bool, pub source: String, pub integrity_verified: bool, pub last_sequence: u64, pub last_receipt_hash: Option<String> }
#[derive(Clone, Deserialize, Serialize)]
pub struct MemoryPageView { pub workspace_path: String, pub state: String, pub project_id: Option<String>, pub store_revision: u64, pub store_digest: Option<String>, pub items: Vec<serde_json::Value>, pub total: u64, pub next_after_revision: Option<u64>, pub side_effect_free: bool }

#[derive(Clone, Deserialize, Serialize)]
pub struct ApprovalReviewView { pub mission_id: String, pub task_id: String, pub approval_id: String, pub approval_version: u32, pub approval_state: String, pub approval_type: Option<String>, pub title: Option<String>, pub reason: Option<String>, pub requested_action: Option<String>, pub risk_category: Option<String>, pub affected_files: Vec<String>, pub operation_count: Option<u32>, pub operation_kinds: Vec<String>, pub plan_id: Option<String>, pub preview_id: Option<String>, pub approval_binding_id: Option<String>, pub digests: std::collections::HashMap<String, String>, pub evidence: Vec<serde_json::Value>, pub preview: Option<serde_json::Value>, pub truncated: bool, pub unavailable_reason: Option<String> }

#[derive(Serialize)]
struct ApprovalDecisionRequest { approval_id: String, approval_version: u32, background: bool }

#[derive(Debug, Serialize)]
pub struct TransportFailure { pub code: &'static str, pub message: &'static str }

impl TransportFailure {
    fn status(self) -> CoreStatus { CoreStatus { state: match self.code { "auth_required" => CoreState::AuthRequired, "protocol_error" => CoreState::ProtocolError, _ => CoreState::CoreError }, code: self.code.to_string(), message: self.message.to_string() } }
}

pub fn resolve_port(value: Option<&str>) -> u16 {
    value.and_then(|raw| raw.trim().parse::<u16>().ok()).filter(|port| (1024..=65535).contains(port)).unwrap_or(DEFAULT_CORE_PORT)
}

pub fn set_runtime_port(port: u16) { RUNTIME_PORT.store(port, Ordering::SeqCst); }
pub fn clear_runtime_port() { RUNTIME_PORT.store(0, Ordering::SeqCst); }
pub fn configured_port() -> u16 { let runtime = RUNTIME_PORT.load(Ordering::SeqCst); if (1024..=65535).contains(&runtime) { runtime } else { resolve_port(env::var("PROMETHEUS_DESKTOP_CORE_PORT").ok().as_deref()) } }

fn client(timeout: Duration) -> Result<Client, TransportFailure> {
    Client::builder().redirect(Policy::none()).connect_timeout(Duration::from_millis(1500)).timeout(timeout).build().map_err(|_| TransportFailure { code: "core_error", message: "Core istemcisi başlatılamadı." })
}

fn endpoint(path: &str) -> String { format!("http://{}:{}{}", CORE_HOST, configured_port(), path) }

fn valid_segment(value: &str) -> bool { !value.is_empty() && value.len() <= 160 && value.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_' || b == b'.') }

fn mission_path(mission_id: &str, suffix: &str) -> Result<String, TransportFailure> {
    if !valid_segment(mission_id) { return Err(TransportFailure { code: "invalid_identifier", message: "Mission kimliği geçersiz." }); }
    Ok(endpoint(&format!("/v1/supervisor/commands/{mission_id}{suffix}")))
}

fn task_path(mission_id: &str, task_id: &str, action: &str) -> Result<String, TransportFailure> {
    if !valid_segment(task_id) { return Err(TransportFailure { code: "invalid_identifier", message: "Görev kimliği geçersiz." }); }
    Ok(mission_path(mission_id, &format!("/tasks/{task_id}/{action}"))?)
}

fn review_path(mission_id: &str, approval_id: &str) -> Result<String, TransportFailure> {
    if !valid_segment(approval_id) { return Err(TransportFailure { code: "invalid_identifier", message: "Onay kimliği geçersiz." }); }
    mission_path(mission_id, &format!("/approvals/{approval_id}/review"))
}

async fn response_json<T: for<'de> Deserialize<'de>>(response: reqwest::Response) -> Result<T, TransportFailure> {
    let status = response.status();
    let body = bounded_body(response).await?;
    if status == StatusCode::UNAUTHORIZED { return Err(TransportFailure { code: "auth_required", message: "Core kimlik doğrulaması gerekli." }); }
    if status == StatusCode::NOT_FOUND { return Err(TransportFailure { code: "not_found", message: "Mission veya görev bulunamadı." }); }
    if status == StatusCode::CONFLICT { return Err(TransportFailure { code: "conflict", message: "Core durumu değişti; güncel durum yeniden yüklenmeli." }); }
    if status == StatusCode::BAD_REQUEST || status == StatusCode::UNPROCESSABLE_ENTITY { return Err(TransportFailure { code: "invalid_request", message: "Core isteği geçersiz." }); }
    if !status.is_success() { return Err(TransportFailure { code: "protocol_error", message: "Core beklenmeyen bir yanıt verdi." }); }
    serde_json::from_slice(&body).map_err(|_| TransportFailure { code: "protocol_error", message: "Core yanıtı geçersiz." })
}

pub async fn mission(mission_id: String) -> Result<MissionView, TransportFailure> {
    let client = client(Duration::from_secs(10))?;
    let response = auth_header(client.get(mission_path(&mission_id, "").map_err(|_| TransportFailure { code: "invalid_identifier", message: "Mission kimliği geçersiz." })?)).send().await.map_err(|_| TransportFailure { code: "core_offline", message: "Core bağlantısı kesildi." })?;
    response_json(response).await
}

pub async fn mission_events(mission_id: String) -> Result<MissionEventsView, TransportFailure> {
    let client = client(Duration::from_secs(10))?;
    let path = mission_path(&mission_id, "/mission-events?limit=50").map_err(|_| TransportFailure { code: "invalid_identifier", message: "Mission kimliği geçersiz." })?;
    let response = auth_header(client.get(path)).send().await.map_err(|_| TransportFailure { code: "core_offline", message: "Core bağlantısı kesildi." })?;
    response_json(response).await
}
pub async fn mission_history(mission_id: String) -> Result<MissionHistoryView, TransportFailure> { let client = client(Duration::from_secs(10))?; let path = mission_path(&mission_id, "/history?limit=50").map_err(|_| TransportFailure { code: "invalid_identifier", message: "Mission kimliği geçersiz." })?; let response = auth_header(client.get(path)).send().await.map_err(|_| TransportFailure { code: "core_offline", message: "Core bağlantısı kesildi." })?; response_json(response).await }
pub async fn mission_receipts(mission_id: String) -> Result<ReceiptPageView, TransportFailure> { let client = client(Duration::from_secs(10))?; let path = mission_path(&mission_id, "/execution-receipts?limit=50").map_err(|_| TransportFailure { code: "invalid_identifier", message: "Mission kimliği geçersiz." })?; let response = auth_header(client.get(path)).send().await.map_err(|_| TransportFailure { code: "core_offline", message: "Core bağlantısı kesildi." })?; response_json(response).await }
pub async fn mission_memory(mission_id: String) -> Result<MemoryPageView, TransportFailure> { let client = client(Duration::from_secs(10))?; let path = mission_path(&mission_id, "/memory").map_err(|_| TransportFailure { code: "invalid_identifier", message: "Mission kimliği geçersiz." })?; let response = auth_header(client.get(path)).send().await.map_err(|_| TransportFailure { code: "core_offline", message: "Core bağlantısı kesildi." })?; response_json(response).await }

pub async fn approval_review(mission_id: String, approval_id: String) -> Result<ApprovalReviewView, TransportFailure> {
    let client = client(Duration::from_secs(10))?;
    let path = review_path(&mission_id, &approval_id).map_err(|_| TransportFailure { code: "invalid_identifier", message: "Mission veya onay kimliği geçersiz." })?;
    let response = auth_header(client.get(path)).send().await.map_err(|_| TransportFailure { code: "core_offline", message: "Core bağlantısı kesildi." })?;
    response_json(response).await
}

async fn decide_task(mission_id: String, task_id: String, approval_id: String, approval_version: u32, action: &str) -> Result<MissionView, TransportFailure> {
    if !valid_segment(&approval_id) || approval_version == 0 { return Err(TransportFailure { code: "invalid_identifier", message: "Onay kimliği geçersiz." }); }
    let client = client(Duration::from_secs(120))?;
    let path = task_path(&mission_id, &task_id, action).map_err(|_| TransportFailure { code: "invalid_identifier", message: "Mission veya görev kimliği geçersiz." })?;
    let response = auth_header(client.post(path).header(CSRF_HEADER_NAME, CSRF_HEADER_VALUE).json(&ApprovalDecisionRequest { approval_id, approval_version, background: true })).send().await.map_err(|_| TransportFailure { code: "uncertain", message: "Karar iletimi belirsiz; otomatik tekrar yapılmadı." })?;
    response_json(response).await
}

pub async fn approve_task(mission_id: String, task_id: String, approval_id: String, approval_version: u32) -> Result<MissionView, TransportFailure> { decide_task(mission_id, task_id, approval_id, approval_version, "approve").await }
pub async fn reject_task(mission_id: String, task_id: String, approval_id: String, approval_version: u32) -> Result<MissionView, TransportFailure> { decide_task(mission_id, task_id, approval_id, approval_version, "reject").await }

async fn bounded_body(response: reqwest::Response) -> Result<Vec<u8>, TransportFailure> {
    if response.content_length().is_some_and(|length| length as usize > MAX_RESPONSE_BYTES) { return Err(TransportFailure { code: "protocol_error", message: "Core yanıtı izin verilen boyutu aşıyor." }); }
    let bytes = response.bytes().await.map_err(|_| TransportFailure { code: "protocol_error", message: "Core yanıtı okunamadı." })?;
    if bytes.len() > MAX_RESPONSE_BYTES { return Err(TransportFailure { code: "protocol_error", message: "Core yanıtı izin verilen boyutu aşıyor." }); }
    Ok(bytes.to_vec())
}

fn auth_header(request: reqwest::RequestBuilder) -> reqwest::RequestBuilder {
    match env::var("HTTP_AUTH_TOKEN").ok().filter(|token| !token.is_empty()) { Some(token) => request.bearer_auth(token), None => request }
}

pub async fn health() -> CoreStatus {
    let client = match client(Duration::from_millis(3000)) { Ok(value) => value, Err(error) => return error.status() };
    let request = auth_header(client.get(endpoint("/v1/health")));
    let response = match request.send().await { Ok(value) => value, Err(error) if error.is_timeout() => return CoreStatus { state: CoreState::CoreError, code: "timeout".to_string(), message: "Core bağlantısı zaman aşımına uğradı.".to_string() }, Err(_) => return CoreStatus { state: CoreState::NotRunning, code: "core_offline".to_string(), message: "Core çevrimdışı.".to_string() } };
    if response.status() == StatusCode::UNAUTHORIZED { return CoreStatus { state: CoreState::AuthRequired, code: "auth_required".to_string(), message: "Core kimlik doğrulaması gerekli.".to_string() }; }
    if !response.status().is_success() { return CoreStatus { state: CoreState::ProtocolError, code: "protocol_error".to_string(), message: "Core beklenmeyen bir yanıt verdi.".to_string() }; }
    match bounded_body(response).await { Ok(_) => CoreStatus { state: CoreState::Ready, code: "ready".to_string(), message: "Core hazır.".to_string() }, Err(error) => error.status() }
}

pub async fn desktop_model_catalog() -> Result<DesktopModelCatalog, TransportFailure> {
    let client = client(Duration::from_secs(10))?;
    let response = auth_header(client.get(endpoint("/v1/desktop/model-catalog"))).send().await.map_err(|_| TransportFailure { code: "core_offline", message: "Core bağlantısı kesildi." })?;
    response_json(response).await
}

pub async fn submit(message: String) -> Result<DesktopCommandResponse, TransportFailure> {
    let client = client(Duration::from_secs(120))?;
    let request = auth_header(client.post(endpoint("/v1/desktop/command")).header(CSRF_HEADER_NAME, CSRF_HEADER_VALUE).json(&DesktopCommandRequest { message }));
    let response = request.send().await.map_err(|error| if error.is_timeout() { TransportFailure { code: "timeout", message: "Core bağlantısı zaman aşımına uğradı." } } else { TransportFailure { code: "core_offline", message: "Core bağlantısı kesildi. Komut otomatik olarak yeniden gönderilmedi." } })?;
    let status = response.status();
    let body = bounded_body(response).await?;
    if status == StatusCode::UNAUTHORIZED { return Err(TransportFailure { code: "auth_required", message: "Core kimlik doğrulaması gerekli." }); }
    if status == StatusCode::FORBIDDEN { return Err(TransportFailure { code: "forbidden", message: "Core isteği reddetti." }); }
    if status == StatusCode::BAD_REQUEST || status == StatusCode::UNPROCESSABLE_ENTITY { return Err(TransportFailure { code: "invalid_request", message: "Komut geçersiz." }); }
    if status.is_server_error() { return Err(TransportFailure { code: "core_internal", message: "Core komutu işleyemedi." }); }
    if !status.is_success() { return Err(TransportFailure { code: "protocol_error", message: "Core beklenmeyen bir yanıt verdi." }); }
    serde_json::from_slice(&body).map_err(|_| TransportFailure { code: "protocol_error", message: "Core yanıtı geçersiz." })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn default_port_is_loopback_contract() { assert_eq!(resolve_port(None), 8765); assert!(endpoint("/v1/health").starts_with("http://127.0.0.1:")); }
    #[test] fn port_override_is_bounded() { assert_eq!(resolve_port(Some("4321")), 4321); assert_eq!(resolve_port(Some("80")), 8765); assert_eq!(resolve_port(Some("65536")), 8765); assert_eq!(resolve_port(Some("nope")), 8765); }
    #[test] fn canonical_endpoints_are_loopback_only() { assert_eq!(CORE_HOST, "127.0.0.1"); assert_eq!(endpoint("/v1/health"), "http://127.0.0.1:8765/v1/health"); assert_eq!(endpoint("/v1/desktop/command"), "http://127.0.0.1:8765/v1/desktop/command"); }
    #[test] fn mission_and_approval_paths_are_bounded() { assert!(mission_path("mission-1", "").unwrap().ends_with("/mission-1")); assert!(mission_path("mission-1", "/history?limit=50").unwrap().ends_with("/history?limit=50")); assert!(mission_path("mission-1", "/execution-receipts?limit=50").is_ok()); assert!(task_path("mission-1", "task-1", "approve").unwrap().ends_with("/tasks/task-1/approve")); assert!(review_path("mission-1", "approval-1").unwrap().ends_with("/approvals/approval-1/review")); assert!(mission_path("../escape", "").is_err()); assert!(task_path("mission-1", "task/escape", "reject").is_err()); assert!(review_path("mission-1", "approval/escape").is_err()); assert!(valid_segment("approval-1")); assert!(!valid_segment("")); }
}
