export type NavigationView='home'|'command'|'projects'|'missions'|'approvals'|'changes'|'agents'|'activity'|'memory'|'settings';
export type CoreConnectionState='not_running'|'connecting'|'ready'|'auth_required'|'protocol_error'|'core_error'|'timeout'|'preview';
export interface CoreStatus{state:CoreConnectionState;code:string;message:string}
export interface DesktopCommandRequest{message:string}
export interface DesktopCommandResponse{status:string;mission_id:string;summary:string|null;requires_approval:boolean}
export interface MissionTask{ id:string; title:string; status:string; assigned_agent:string; approval_id:string|null; approval_version:number; approval_state:string; approval_description:string|null; approval_preview:unknown|null; approval_tool:string|null; last_approval_message:string|null }
export interface Mission{ id:string; goal:string; status:string; tasks:MissionTask[]; created_at:string; updated_at?:string|null; operation_message?:string|null; failure_reason?:string|null }
export interface MissionEvent{ sequence:number; event_type:string; message:string; occurred_at:string; task_id:string|null; approval_id:string|null }
export interface MissionEvents{ mission_id:string; events:MissionEvent[]; count:number; has_more:boolean }
export interface AuthorityDescriptor{webviewFilesystem:boolean;webviewShell:boolean;webviewProcess:boolean;webviewRemoteNetwork:boolean;canonicalAuthority:string}
export interface DesktopBootstrap{revision:string;product:string;surface:string;native:boolean;core:{state:string;detail:string};authority:AuthorityDescriptor}
export interface CommandDefinition{id:string;label:string;group:string;keywords:string[];view:NavigationView;icon:string}
