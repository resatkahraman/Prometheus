# ADR-039: Bounded Native OS Integration

Status: Accepted and validated.

Native operating-system effects are exposed only through dedicated typed Tauri commands. The webview receives no direct clipboard, dialog, notification, opener, filesystem, shell or process plugin permission.

File and folder paths become revealable only after explicit native-dialog selection and exact canonical-path registration. Traversal and unregistered paths fail closed. General default-handler file opening is intentionally unavailable. External browser handoff accepts only parsed HTTPS URLs without embedded credentials.

Clipboard operations are explicit text-only actions bounded to 64 KiB. Notifications have centralized title/body limits. No operation consumes model output directly, creates generic process authority, records sensitive contents or performs background harvesting.
