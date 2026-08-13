mod bridge;
mod core_transport;
mod core_runtime;
mod native_os;
use tauri::Manager;
use std::sync::atomic::{AtomicBool, Ordering};

struct ShutdownState(AtomicBool);

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .manage(native_os::NativeOsState::default())
        .manage(ShutdownState(AtomicBool::new(false)))
        .manage(std::sync::Arc::new(std::sync::Mutex::new(core_runtime::CoreRuntime::new())))
        .setup(|app| {
            let handle = app.handle().clone();
            let runtime = app.state::<core_runtime::SharedRuntime>().inner().clone();
            tauri::async_runtime::spawn(async move {
                let _ = core_runtime::start(handle, runtime).await;
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bridge::desktop_bootstrap, bridge::desktop_core_status, bridge::desktop_model_catalog,
            bridge::desktop_runtime_status, bridge::desktop_start_core, bridge::desktop_stop_core,
            bridge::desktop_submit_command, bridge::desktop_mission, bridge::desktop_mission_events,
            bridge::desktop_mission_history, bridge::desktop_mission_receipts, bridge::desktop_mission_memory,
            bridge::desktop_approval_review, bridge::desktop_approve_task, bridge::desktop_reject_task,
            bridge::desktop_native_environment, bridge::desktop_native_capabilities,
            bridge::desktop_native_select_file, bridge::desktop_native_select_folder,
            bridge::desktop_native_reveal_path, bridge::desktop_native_read_clipboard,
            bridge::desktop_native_write_clipboard, bridge::desktop_native_notify,
            bridge::desktop_native_open_external_url,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Prometheus")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = event {
                let shutdown = app_handle.state::<ShutdownState>();
                if shutdown.0.swap(true, Ordering::SeqCst) { return; }
                api.prevent_exit();
                let runtime = app_handle.state::<core_runtime::SharedRuntime>().inner().clone();
                let handle = app_handle.clone();
                tauri::async_runtime::spawn(async move {
                    let _ = core_runtime::stop(runtime).await;
                    handle.exit(0);
                });
            }
        });
}
