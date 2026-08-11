mod bridge;
mod core_transport;
#[cfg_attr(mobile, tauri::mobile_entry_point)]pub fn run(){tauri::Builder::default().invoke_handler(tauri::generate_handler![bridge::desktop_bootstrap, bridge::desktop_core_status, bridge::desktop_submit_command, bridge::desktop_mission, bridge::desktop_mission_events, bridge::desktop_approve_task, bridge::desktop_reject_task]).run(tauri::generate_context!()).expect("error while running Prometheus");}
