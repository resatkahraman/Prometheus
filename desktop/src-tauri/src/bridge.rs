use serde::Serialize;
use crate::core_runtime::{self, RuntimeStatus, SharedRuntime};
use crate::core_transport::{self, ApprovalReviewView, CoreStatus, DesktopCommandResponse, DesktopConversationTurn, DesktopModelCatalog, MemoryPageView, MissionEventsView, MissionHistoryView, MissionView, ReceiptPageView, TransportFailure};
use crate::native_os::{self, NativeCapability, NativeEnvironmentInfo, NativeOsError, NativeOsState};
#[derive(Serialize)]pub struct Bootstrap{revision:&'static str,product:&'static str,surface:&'static str,native:bool,core:Core,authority:Authority}
#[derive(Serialize)]struct Core{state:&'static str,detail:&'static str}
#[derive(Serialize)]struct Authority{#[serde(rename="webviewFilesystem")]webview_filesystem:bool,#[serde(rename="webviewShell")]webview_shell:bool,#[serde(rename="webviewProcess")]webview_process:bool,#[serde(rename="webviewRemoteNetwork")]webview_remote_network:bool,#[serde(rename="canonicalAuthority")]canonical_authority:&'static str}
#[tauri::command]pub fn desktop_bootstrap()->Bootstrap{Bootstrap{revision:"prometheus-desktop-bridge-v2",product:"Prometheus",surface:"desktop",native:true,core:Core{state:"transport_available",detail:"Loopback Core transport available."},authority:Authority{webview_filesystem:false,webview_shell:false,webview_process:false,webview_remote_network:false,canonical_authority:"prometheus-core"}}}
#[tauri::command]pub async fn desktop_core_status()->CoreStatus{core_transport::health().await}
#[tauri::command]pub async fn desktop_model_catalog()->Result<DesktopModelCatalog,TransportFailure>{core_transport::desktop_model_catalog().await}
#[tauri::command]pub async fn desktop_runtime_status(state:tauri::State<'_, SharedRuntime>)->Result<RuntimeStatus,String>{let runtime=state.inner().clone();Ok(core_runtime::status(runtime).await)}
#[tauri::command]pub async fn desktop_start_core(app:tauri::AppHandle,state:tauri::State<'_, SharedRuntime>)->Result<RuntimeStatus,String>{core_runtime::start(app,state.inner().clone()).await}
#[tauri::command]pub async fn desktop_stop_core(state:tauri::State<'_, SharedRuntime>)->Result<RuntimeStatus,String>{core_runtime::stop(state.inner().clone()).await}
#[tauri::command]pub async fn desktop_submit_command(message:String,history:Vec<DesktopConversationTurn>)->Result<DesktopCommandResponse,TransportFailure>{core_transport::submit(message,history).await}
#[tauri::command]pub async fn desktop_mission(mission_id:String)->Result<MissionView,TransportFailure>{core_transport::mission(mission_id).await}
#[tauri::command]pub async fn desktop_mission_events(mission_id:String)->Result<MissionEventsView,TransportFailure>{core_transport::mission_events(mission_id).await}
#[tauri::command]pub async fn desktop_mission_history(mission_id:String)->Result<MissionHistoryView,TransportFailure>{core_transport::mission_history(mission_id).await}
#[tauri::command]pub async fn desktop_mission_receipts(mission_id:String)->Result<ReceiptPageView,TransportFailure>{core_transport::mission_receipts(mission_id).await}
#[tauri::command]pub async fn desktop_mission_memory(mission_id:String)->Result<MemoryPageView,TransportFailure>{core_transport::mission_memory(mission_id).await}
#[tauri::command]pub async fn desktop_approval_review(mission_id:String,approval_id:String)->Result<ApprovalReviewView,TransportFailure>{core_transport::approval_review(mission_id,approval_id).await}
#[tauri::command]pub async fn desktop_approve_task(mission_id:String,task_id:String,approval_id:String,approval_version:u32)->Result<MissionView,TransportFailure>{core_transport::approve_task(mission_id,task_id,approval_id,approval_version).await}
#[tauri::command]pub async fn desktop_reject_task(mission_id:String,task_id:String,approval_id:String,approval_version:u32)->Result<MissionView,TransportFailure>{core_transport::reject_task(mission_id,task_id,approval_id,approval_version).await}
#[tauri::command]pub fn desktop_native_environment(app:tauri::AppHandle)->NativeEnvironmentInfo{native_os::environment(&app)}
#[tauri::command]pub fn desktop_native_capabilities()->Vec<NativeCapability>{native_os::capabilities()}
#[tauri::command]pub fn desktop_native_select_file(app:tauri::AppHandle,state:tauri::State<'_,NativeOsState>)->Result<Option<String>,NativeOsError>{native_os::select_file(&app,&state)}
#[tauri::command]pub fn desktop_native_select_folder(app:tauri::AppHandle,state:tauri::State<'_,NativeOsState>)->Result<Option<String>,NativeOsError>{native_os::select_folder(&app,&state)}
#[tauri::command]pub fn desktop_native_reveal_path(app:tauri::AppHandle,state:tauri::State<'_,NativeOsState>,path:String)->Result<(),NativeOsError>{native_os::reveal_path(&app,&state,&path)}
#[tauri::command]pub fn desktop_native_read_clipboard(app:tauri::AppHandle)->Result<String,NativeOsError>{native_os::read_clipboard(&app)}
#[tauri::command]pub fn desktop_native_write_clipboard(app:tauri::AppHandle,text:String)->Result<(),NativeOsError>{native_os::write_clipboard(&app,text)}
#[tauri::command]pub fn desktop_native_notify(app:tauri::AppHandle,title:String,body:String)->Result<(),NativeOsError>{native_os::notify(&app,title,body)}
#[tauri::command]pub fn desktop_native_open_external_url(app:tauri::AppHandle,url:String)->Result<(),NativeOsError>{native_os::open_external_url(&app,url)}
