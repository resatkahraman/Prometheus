export type NavigationView='home'|'command'|'projects'|'missions'|'approvals'|'changes'|'agents'|'activity'|'memory'|'settings';
export type CoreConnectionState='not_running'|'connecting'|'ready'|'auth_required'|'protocol_error'|'core_error'|'timeout'|'preview';
export interface CoreStatus{state:CoreConnectionState;code:string;message:string}
export interface DesktopCommandRequest{message:string}
export interface DesktopCommandResponse{status:string;mission_id:string;summary:string|null;requires_approval:boolean}
export interface AuthorityDescriptor{webviewFilesystem:boolean;webviewShell:boolean;webviewProcess:boolean;webviewRemoteNetwork:boolean;canonicalAuthority:string}
export interface DesktopBootstrap{revision:string;product:string;surface:string;native:boolean;core:{state:string;detail:string};authority:AuthorityDescriptor}
export interface CommandDefinition{id:string;label:string;group:string;keywords:string[];view:NavigationView;icon:string}
