use reqwest::{redirect::Policy, Client, StatusCode};
use serde::{Deserialize, Serialize};
use std::env;
use std::time::Duration;

pub const CORE_HOST: &str = "127.0.0.1";
pub const DEFAULT_CORE_PORT: u16 = 8765;
const MAX_RESPONSE_BYTES: usize = 1024 * 1024;

#[derive(Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum CoreState { NotRunning, Ready, AuthRequired, ProtocolError, CoreError }

#[derive(Clone, Serialize)]
pub struct CoreStatus { pub state: CoreState, pub code: String, pub message: String }

#[derive(Serialize)]
pub struct DesktopCommandRequest { pub message: String }

#[derive(Deserialize, Serialize)]
pub struct DesktopCommandResponse { pub status: String, pub mission_id: String, pub summary: Option<String>, pub requires_approval: bool }

#[derive(Debug, Serialize)]
pub struct TransportFailure { pub code: &'static str, pub message: &'static str }

impl TransportFailure {
    fn status(self) -> CoreStatus { CoreStatus { state: match self.code { "auth_required" => CoreState::AuthRequired, "protocol_error" => CoreState::ProtocolError, _ => CoreState::CoreError }, code: self.code.to_string(), message: self.message.to_string() } }
}

pub fn resolve_port(value: Option<&str>) -> u16 {
    value.and_then(|raw| raw.trim().parse::<u16>().ok()).filter(|port| (1024..=65535).contains(port)).unwrap_or(DEFAULT_CORE_PORT)
}

pub fn configured_port() -> u16 { resolve_port(env::var("PROMETHEUS_DESKTOP_CORE_PORT").ok().as_deref()) }

fn client(timeout: Duration) -> Result<Client, TransportFailure> {
    Client::builder().redirect(Policy::none()).connect_timeout(Duration::from_millis(1500)).timeout(timeout).build().map_err(|_| TransportFailure { code: "core_error", message: "Core istemcisi başlatılamadı." })
}

fn endpoint(path: &str) -> String { format!("http://{}:{}{}", CORE_HOST, configured_port(), path) }

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

pub async fn submit(message: String) -> Result<DesktopCommandResponse, TransportFailure> {
    let client = client(Duration::from_secs(120))?;
    let request = auth_header(client.post(endpoint("/v1/desktop/command")).json(&DesktopCommandRequest { message }));
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
}
