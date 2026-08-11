mod bridge;
mod core_transport;
mod core_runtime;
#[cfg_attr(mobile, tauri::mobile_entry_point)]pub fn run(){tauri::Builder::default().manage(std::sync::Arc::new(std::sync::Mutex::new(core_runtime::CoreRuntime::new()))).invoke_handler(tauri::generate_handler![bridge::desktop_bootstrap, bridge::desktop_core_status, bridge::desktop_runtime_status, bridge::desktop_start_core, bridge::desktop_stop_core, bridge::desktop_submit_command, bridge::desktop_mission, bridge::desktop_mission_events, bridge::desktop_mission_history, bridge::desktop_mission_receipts, bridge::desktop_mission_memory, bridge::desktop_approval_review, bridge::desktop_approve_task, bridge::desktop_reject_task]).run(tauri::generate_context!()).expect("error while running Prometheus");}
