use serde::Serialize;
use crate::core_transport::{self, CoreStatus, DesktopCommandResponse, TransportFailure};
#[derive(Serialize)]pub struct Bootstrap{revision:&'static str,product:&'static str,surface:&'static str,native:bool,core:Core,authority:Authority}
#[derive(Serialize)]struct Core{state:&'static str,detail:&'static str}
#[derive(Serialize)]struct Authority{#[serde(rename="webviewFilesystem")]webview_filesystem:bool,#[serde(rename="webviewShell")]webview_shell:bool,#[serde(rename="webviewProcess")]webview_process:bool,#[serde(rename="webviewRemoteNetwork")]webview_remote_network:bool,#[serde(rename="canonicalAuthority")]canonical_authority:&'static str}
#[tauri::command]pub fn desktop_bootstrap()->Bootstrap{Bootstrap{revision:"prometheus-desktop-bridge-v2",product:"Prometheus",surface:"desktop",native:true,core:Core{state:"transport_available",detail:"Loopback Core transport available."},authority:Authority{webview_filesystem:false,webview_shell:false,webview_process:false,webview_remote_network:false,canonical_authority:"prometheus-core"}}}
#[tauri::command]pub async fn desktop_core_status()->CoreStatus{core_transport::health().await}
#[tauri::command]pub async fn desktop_submit_command(message:String)->Result<DesktopCommandResponse,TransportFailure>{core_transport::submit(message).await}
