import { invoke } from '@tauri-apps/api/core';
import type { ApprovalReview, CoreStatus, DesktopBootstrap, DesktopCommandResponse, DesktopModelCatalog, MemoryPage, Mission, MissionEvents, MissionHistory, NativeCapability, NativeEnvironmentInfo, ReceiptPage, RuntimeStatus } from '../types/desktop';

const native = () => '__TAURI_INTERNALS__' in window;
const previewStatus: CoreStatus = { state: 'preview', code: 'preview', message: 'Core transport is available only in the native application.' };

export async function getDesktopBootstrap(): Promise<DesktopBootstrap> {
  if (!native()) return { revision: 'prometheus-desktop-bridge-v2', product: 'Prometheus', surface: 'desktop', native: false, core: { state: 'preview', detail: previewStatus.message }, authority: { webviewFilesystem: false, webviewShell: false, webviewProcess: false, webviewRemoteNetwork: false, canonicalAuthority: 'prometheus-core' } };
  return invoke<DesktopBootstrap>('desktop_bootstrap');
}

export async function getDesktopCoreStatus(): Promise<CoreStatus> {
  if (!native()) return previewStatus;
  return invoke<CoreStatus>('desktop_core_status');
}

export async function submitDesktopCommand(message: string): Promise<DesktopCommandResponse> {
  if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' };
  return invoke<DesktopCommandResponse>('desktop_submit_command', { message });
}

export async function getDesktopMission(missionId: string): Promise<Mission> {
  if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' };
  return invoke<Mission>('desktop_mission', { missionId });
}

export async function getDesktopMissionEvents(missionId: string): Promise<MissionEvents> {
  if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' };
  return invoke<MissionEvents>('desktop_mission_events', { missionId });
}
export async function getDesktopRuntimeStatus(): Promise<RuntimeStatus> { if (!native()) return { connectivity: 'offline', ownership: 'none', lifecycle: 'launch_unavailable', can_start: false, can_stop: false, message_code: 'preview', message: 'Core lifecycle is available only in the native application.' }; return invoke<RuntimeStatus>('desktop_runtime_status'); }
export async function getDesktopModelCatalog(): Promise<DesktopModelCatalog> { if (!native()) throw { code: 'launch_unavailable', message: 'Model catalog is available only in the native application.' }; return invoke<DesktopModelCatalog>('desktop_model_catalog'); }
export async function startDesktopCore(): Promise<RuntimeStatus> { if (!native()) throw { code: 'launch_unavailable', message: 'Core lifecycle is available only in the native application.' }; return invoke<RuntimeStatus>('desktop_start_core'); }
export async function stopDesktopCore(): Promise<RuntimeStatus> { if (!native()) throw { code: 'stop_not_authorized', message: 'Core lifecycle is available only in the native application.' }; return invoke<RuntimeStatus>('desktop_stop_core'); }
export async function getDesktopMissionHistory(missionId: string): Promise<MissionHistory> { if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' }; return invoke<MissionHistory>('desktop_mission_history', { missionId }); }
export async function getDesktopMissionReceipts(missionId: string): Promise<ReceiptPage> { if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' }; return invoke<ReceiptPage>('desktop_mission_receipts', { missionId }); }
export async function getDesktopMissionMemory(missionId: string): Promise<MemoryPage> { if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' }; return invoke<MemoryPage>('desktop_mission_memory', { missionId }); }

export async function getDesktopApprovalReview(missionId: string, approvalId: string): Promise<ApprovalReview> {
  if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' };
  return invoke<ApprovalReview>('desktop_approval_review', { missionId, approvalId });
}

export async function approveDesktopTask(missionId: string, taskId: string, approvalId: string, approvalVersion: number): Promise<Mission> {
  if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' };
  return invoke<Mission>('desktop_approve_task', { missionId, taskId, approvalId, approvalVersion });
}

export async function rejectDesktopTask(missionId: string, taskId: string, approvalId: string, approvalVersion: number): Promise<Mission> {
  if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' };
  return invoke<Mission>('desktop_reject_task', { missionId, taskId, approvalId, approvalVersion });
}

const nativeOnly = () => { if (!native()) throw { code: 'not_available', message: 'Native integration is available only in the installed application.' }; };
export async function getNativeEnvironment(): Promise<NativeEnvironmentInfo> { nativeOnly(); return invoke<NativeEnvironmentInfo>('desktop_native_environment'); }
export async function getNativeCapabilities(): Promise<NativeCapability[]> { nativeOnly(); return invoke<NativeCapability[]>('desktop_native_capabilities'); }
export async function selectNativeFile(): Promise<string | null> { nativeOnly(); return invoke<string | null>('desktop_native_select_file'); }
export async function selectNativeFolder(): Promise<string | null> { nativeOnly(); return invoke<string | null>('desktop_native_select_folder'); }
export async function revealNativePath(path: string): Promise<void> { nativeOnly(); return invoke<void>('desktop_native_reveal_path', { path }); }
export async function readClipboardText(): Promise<string> { nativeOnly(); return invoke<string>('desktop_native_read_clipboard'); }
export async function writeClipboardText(text: string): Promise<void> { nativeOnly(); return invoke<void>('desktop_native_write_clipboard', { text }); }
export async function showNativeNotification(title: string, body: string): Promise<void> { nativeOnly(); return invoke<void>('desktop_native_notify', { title, body }); }
export async function openExternalUrl(url: string): Promise<void> { nativeOnly(); return invoke<void>('desktop_native_open_external_url', { url }); }
