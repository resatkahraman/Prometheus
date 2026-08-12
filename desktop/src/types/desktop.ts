export type NavigationView='home'|'command'|'projects'|'missions'|'approvals'|'changes'|'agents'|'activity'|'memory'|'settings';
export type CoreConnectionState='not_running'|'connecting'|'ready'|'auth_required'|'protocol_error'|'core_error'|'timeout'|'preview';
export interface CoreStatus{state:CoreConnectionState;code:string;message:string}
export type RuntimeLifecycle='offline'|'external_ready'|'external_auth_required'|'port_conflict'|'managed_starting'|'managed_ready'|'managed_stopping'|'managed_exited'|'launch_unavailable'|'launch_failed';
export interface RuntimeStatus{connectivity:string;ownership:string;lifecycle:RuntimeLifecycle;can_start:boolean;can_stop:boolean;message_code:string;message:string}
export interface DesktopModelProfile{route_key:string;canonical_id:string;display_name:string;provider:string;local:boolean;model_class:string;capabilities:string[];enabled:boolean;configured:boolean;availability:string;cost_class:string;configured_context_tokens:number|null}
export interface DesktopModelCatalog{models:DesktopModelProfile[];agents:Record<string,unknown>[];routing_information:string}
export interface NativeCapability{capability_id:string;available:boolean;platform:string;requires_user_gesture:boolean}
export interface NativeEnvironmentInfo{os_family:string;architecture:string;application_version:string;runtime_platform:string}
export interface DesktopCommandRequest{message:string}
export interface DesktopCommandResponse{status:string;mission_id:string;summary:string|null;requires_approval:boolean}
export interface MissionTask{ id:string; title:string; status:string; assigned_agent:string; approval_id:string|null; approval_version:number; approval_state:string; approval_description:string|null; approval_preview:unknown|null; approval_tool:string|null; last_approval_message:string|null }
export interface Mission{ id:string; goal:string; status:string; tasks:MissionTask[]; created_at:string; updated_at?:string|null; operation_message?:string|null; failure_reason?:string|null }
export interface MissionEvent{ sequence:number; event_type:string; message:string; occurred_at:string; task_id:string|null; approval_id:string|null }
export interface MissionEvents{ mission_id:string; events:MissionEvent[]; count:number; has_more:boolean }
export interface MissionHistory{ mission_id:string; command_status:string; terminal:boolean; entries:Record<string,unknown>[]; count:number; after_sequence:number; next_after_sequence:number|null; has_more:boolean; source:string; integrity_verified:boolean; last_sequence:number; last_event_hash:string|null }
export interface ReceiptPage{ mission_id:string; receipts:Record<string,unknown>[]; count:number; after_sequence:number; next_after_sequence:number|null; has_more:boolean; source:string; integrity_verified:boolean; last_sequence:number; last_receipt_hash:string|null }
export interface MemoryPage{ workspace_path:string; state:string; project_id:string|null; store_revision:number; store_digest:string|null; items:Record<string,unknown>[]; total:number; next_after_revision:number|null; side_effect_free:boolean }
export interface ApprovalReview{ mission_id:string; task_id:string; approval_id:string; approval_version:number; approval_state:string; approval_type:string|null; title:string|null; reason:string|null; requested_action:string|null; risk_category:string|null; affected_files:string[]; operation_count:number|null; operation_kinds:string[]; plan_id:string|null; preview_id:string|null; approval_binding_id:string|null; digests:Record<string,string>; evidence:Record<string,unknown>[]; preview:Record<string,unknown>|null; truncated:boolean; unavailable_reason:string|null }
export interface AuthorityDescriptor{webviewFilesystem:boolean;webviewShell:boolean;webviewProcess:boolean;webviewRemoteNetwork:boolean;canonicalAuthority:string}
export interface DesktopBootstrap{revision:string;product:string;surface:string;native:boolean;core:{state:string;detail:string};authority:AuthorityDescriptor}
export interface CommandDefinition{id:string;label:string;group:string;keywords:string[];view:NavigationView;icon:string}
