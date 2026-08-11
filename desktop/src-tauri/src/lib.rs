mod bridge;
mod core_transport;
#[cfg_attr(mobile, tauri::mobile_entry_point)]pub fn run(){tauri::Builder::default().invoke_handler(tauri::generate_handler![bridge::desktop_bootstrap, bridge::desktop_core_status, bridge::desktop_submit_command]).run(tauri::generate_context!()).expect("error while running Prometheus");}
