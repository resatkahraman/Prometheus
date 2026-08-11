import { invoke } from '@tauri-apps/api/core';
import type { CoreStatus, DesktopBootstrap, DesktopCommandResponse, Mission, MissionEvents } from '../types/desktop';

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

export async function approveDesktopTask(missionId: string, taskId: string, approvalId: string, approvalVersion: number): Promise<Mission> {
  if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' };
  return invoke<Mission>('desktop_approve_task', { missionId, taskId, approvalId, approvalVersion });
}

export async function rejectDesktopTask(missionId: string, taskId: string, approvalId: string, approvalVersion: number): Promise<Mission> {
  if (!native()) throw { code: 'core_offline', message: 'Core is available only in the native application.' };
  return invoke<Mission>('desktop_reject_task', { missionId, taskId, approvalId, approvalVersion });
}
