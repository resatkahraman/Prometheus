use serde::Serialize;
#[derive(Serialize)]pub struct Bootstrap{revision:&'static str,product:&'static str,surface:&'static str,native:bool,core:Core,authority:Authority}
#[derive(Serialize)]struct Core{state:&'static str,detail:&'static str}
#[derive(Serialize)]struct Authority{#[serde(rename="webviewFilesystem")]webview_filesystem:bool,#[serde(rename="webviewShell")]webview_shell:bool,#[serde(rename="webviewProcess")]webview_process:bool,#[serde(rename="webviewRemoteNetwork")]webview_remote_network:bool,#[serde(rename="canonicalAuthority")]canonical_authority:&'static str}
#[tauri::command]pub fn desktop_bootstrap()->Bootstrap{Bootstrap{revision:"prometheus-desktop-bridge-v1",product:"Prometheus",surface:"desktop",native:true,core:Core{state:"not_configured",detail:"Core transport is not configured in DESKTOP-001."},authority:Authority{webview_filesystem:false,webview_shell:false,webview_process:false,webview_remote_network:false,canonical_authority:"prometheus-core"}}}
