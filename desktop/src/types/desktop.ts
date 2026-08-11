export type NavigationView='home'|'command'|'projects'|'missions'|'approvals'|'changes'|'agents'|'activity'|'memory'|'settings';
export type CoreConnectionState='not_configured'|'preview'|'native_ready'|'native_error';
export interface AuthorityDescriptor{webviewFilesystem:boolean;webviewShell:boolean;webviewProcess:boolean;webviewRemoteNetwork:boolean;canonicalAuthority:string}
export interface DesktopBootstrap{revision:string;product:string;surface:string;native:boolean;core:{state:string;detail:string};authority:AuthorityDescriptor}
export interface CommandDefinition{id:string;label:string;group:string;keywords:string[];view:NavigationView;icon:string}
