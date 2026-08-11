use serde::Serialize;
use crate::core_runtime::{self, RuntimeStatus, SharedRuntime};
use crate::core_transport::{self, ApprovalReviewView, CoreStatus, DesktopCommandResponse, MemoryPageView, MissionEventsView, MissionHistoryView, MissionView, ReceiptPageView, TransportFailure};
#[derive(Serialize)]pub struct Bootstrap{revision:&'static str,product:&'static str,surface:&'static str,native:bool,core:Core,authority:Authority}
#[derive(Serialize)]struct Core{state:&'static str,detail:&'static str}
#[derive(Serialize)]struct Authority{#[serde(rename="webviewFilesystem")]webview_filesystem:bool,#[serde(rename="webviewShell")]webview_shell:bool,#[serde(rename="webviewProcess")]webview_process:bool,#[serde(rename="webviewRemoteNetwork")]webview_remote_network:bool,#[serde(rename="canonicalAuthority")]canonical_authority:&'static str}
#[tauri::command]pub fn desktop_bootstrap()->Bootstrap{Bootstrap{revision:"prometheus-desktop-bridge-v2",product:"Prometheus",surface:"desktop",native:true,core:Core{state:"transport_available",detail:"Loopback Core transport available."},authority:Authority{webview_filesystem:false,webview_shell:false,webview_process:false,webview_remote_network:false,canonical_authority:"prometheus-core"}}}
#[tauri::command]pub async fn desktop_core_status()->CoreStatus{core_transport::health().await}
#[tauri::command]pub async fn desktop_runtime_status(state:tauri::State<'_, SharedRuntime>)->Result<RuntimeStatus,String>{let runtime=state.inner().clone();Ok(core_runtime::status(runtime).await)}
#[tauri::command]pub async fn desktop_start_core(state:tauri::State<'_, SharedRuntime>)->Result<RuntimeStatus,String>{core_runtime::start(state.inner().clone()).await}
#[tauri::command]pub async fn desktop_stop_core(state:tauri::State<'_, SharedRuntime>)->Result<RuntimeStatus,String>{core_runtime::stop(state.inner().clone()).await}
#[tauri::command]pub async fn desktop_submit_command(message:String)->Result<DesktopCommandResponse,TransportFailure>{core_transport::submit(message).await}
#[tauri::command]pub async fn desktop_mission(mission_id:String)->Result<MissionView,TransportFailure>{core_transport::mission(mission_id).await}
#[tauri::command]pub async fn desktop_mission_events(mission_id:String)->Result<MissionEventsView,TransportFailure>{core_transport::mission_events(mission_id).await}
#[tauri::command]pub async fn desktop_mission_history(mission_id:String)->Result<MissionHistoryView,TransportFailure>{core_transport::mission_history(mission_id).await}
#[tauri::command]pub async fn desktop_mission_receipts(mission_id:String)->Result<ReceiptPageView,TransportFailure>{core_transport::mission_receipts(mission_id).await}
#[tauri::command]pub async fn desktop_mission_memory(mission_id:String)->Result<MemoryPageView,TransportFailure>{core_transport::mission_memory(mission_id).await}
#[tauri::command]pub async fn desktop_approval_review(mission_id:String,approval_id:String)->Result<ApprovalReviewView,TransportFailure>{core_transport::approval_review(mission_id,approval_id).await}
#[tauri::command]pub async fn desktop_approve_task(mission_id:String,task_id:String,approval_id:String,approval_version:u32)->Result<MissionView,TransportFailure>{core_transport::approve_task(mission_id,task_id,approval_id,approval_version).await}
#[tauri::command]pub async fn desktop_reject_task(mission_id:String,task_id:String,approval_id:String,approval_version:u32)->Result<MissionView,TransportFailure>{core_transport::reject_task(mission_id,task_id,approval_id,approval_version).await}
