from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from app.core.schemas import RunFileChange, RunRevertResponse
from app.supervisor.models import SupervisorCommand
from app.workspace.policy import WorkspacePolicy, ToolError


class RunSnapshotManager:
    def __init__(self, storage_root: Path | None = None) -> None:
        self.storage_root = (
            storage_root.expanduser().resolve()
            if storage_root is not None
            else Path(".adam/run_snapshots").resolve()
        )

    def _task_dir(self, command_id: str, task_id: str) -> Path:
        return self.storage_root / command_id / task_id

    def capture_task_snapshot(
        self,
        *,
        command_id: str,
        task_id: str,
        workspace_path: str,
        exact_files: list[str],
        workspace_root: Path,
        max_file_bytes: int = 10_000_000,
        max_search_results: int = 1000,
    ) -> None:
        task_dir = self._task_dir(command_id, task_id)
        manifest_path = task_dir / "manifest.json"

        # Retry preserves first snapshot; do not overwrite valid existing manifest
        if manifest_path.is_file():
            return

        policy = WorkspacePolicy(
            root=workspace_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )

        files_dir = task_dir / "files"
        task_dir.mkdir(parents=True, exist_ok=True)
        files_dir.mkdir(parents=True, exist_ok=True)

        files_manifest: list[dict[str, Any]] = []

        for raw_path in exact_files:
            try:
                resolved = policy.resolve(raw_path, must_exist=False)
                policy.ensure_not_sensitive(resolved)
                rel_path = resolved.relative_to(policy.root).as_posix()
            except (ToolError, ValueError, OSError) as exc:
                raise ValueError(
                    f"Sensitive veya geçersiz path snapshot'a alınamaz '{raw_path}': {exc}"
                ) from exc

            if resolved.is_file():
                file_bytes = resolved.read_bytes()
                if len(file_bytes) > max_file_bytes:
                    raise ValueError(
                        f"Dosya boyutu snapshot limitini aşıyor: {rel_path}"
                    )
                sha256_before = hashlib.sha256(file_bytes).hexdigest()
                size_before = len(file_bytes)
                blob_rel = f"files/{sha256_before}.bin"
                blob_path = files_dir / f"{sha256_before}.bin"

                if not blob_path.is_file():
                    with tempfile.NamedTemporaryFile("wb", dir=files_dir, delete=False) as tf:
                        tf.write(file_bytes)
                        tmp_name = tf.name
                    shutil.move(tmp_name, blob_path)

                files_manifest.append(
                    {
                        "relative_path": rel_path,
                        "existed_before": True,
                        "sha256_before": sha256_before,
                        "size_before": size_before,
                        "blob": blob_rel,
                    }
                )
            else:
                files_manifest.append(
                    {
                        "relative_path": rel_path,
                        "existed_before": False,
                        "sha256_before": None,
                        "size_before": None,
                        "blob": None,
                    }
                )

        manifest_data = {
            "version": 1,
            "command_id": command_id,
            "task_id": task_id,
            "workspace_path": workspace_path,
            "files": files_manifest,
        }

        with tempfile.NamedTemporaryFile("w", dir=task_dir, delete=False, encoding="utf-8") as tf:
            json.dump(manifest_data, tf, indent=2, ensure_ascii=False)
            tmp_manifest = tf.name
        shutil.move(tmp_manifest, manifest_path)

    def record_task_completion_snapshot(
        self,
        *,
        command_id: str,
        task_id: str,
        workspace_root: Path,
        max_file_bytes: int = 10_000_000,
        max_search_results: int = 1000,
    ) -> None:
        task_dir = self._task_dir(command_id, task_id)
        manifest_path = task_dir / "manifest.json"
        if not manifest_path.is_file():
            return
        policy = WorkspacePolicy(
            root=workspace_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            for entry in data.get("files", []):
                rel = entry["relative_path"]
                try:
                    resolved = policy.resolve(rel, must_exist=False)
                    if resolved.is_file():
                        after_bytes = resolved.read_bytes()
                        entry["sha256_after"] = hashlib.sha256(after_bytes).hexdigest()
                        entry["size_after"] = len(after_bytes)
                        entry["exists_after"] = True
                    else:
                        entry["sha256_after"] = None
                        entry["size_after"] = None
                        entry["exists_after"] = False
                except Exception:
                    pass
            with tempfile.NamedTemporaryFile("w", dir=task_dir, delete=False, encoding="utf-8") as tf:
                json.dump(data, tf, indent=2, ensure_ascii=False)
                tmp_manifest = tf.name
            shutil.move(tmp_manifest, manifest_path)
        except Exception:
            pass

    def _read_command_snapshots(self, command_id: str) -> dict[str, dict[str, Any]]:
        cmd_dir = self.storage_root / command_id
        if not cmd_dir.is_dir():
            return {}

        earliest_file_snapshots: dict[str, dict[str, Any]] = {}

        for task_dir in sorted(cmd_dir.iterdir()):
            manifest_file = task_dir / "manifest.json"
            if not manifest_file.is_file():
                continue
            try:
                data = json.loads(manifest_file.read_text(encoding="utf-8"))
                for entry in data.get("files", []):
                    rel = entry["relative_path"]
                    if rel not in earliest_file_snapshots:
                        earliest_file_snapshots[rel] = {
                            "entry": entry,
                            "task_dir": task_dir,
                        }
                    else:
                        # Update recorded completion after state if present
                        if "sha256_after" in entry:
                            earliest_file_snapshots[rel]["entry"]["sha256_after"] = entry["sha256_after"]
                            earliest_file_snapshots[rel]["entry"]["size_after"] = entry.get("size_after")
                            earliest_file_snapshots[rel]["entry"]["exists_after"] = entry.get("exists_after")
            except Exception:
                continue

        return earliest_file_snapshots

    def build_command_change_review(
        self,
        *,
        command: SupervisorCommand,
        workspace_root: Path,
        max_file_bytes: int = 10_000_000,
        max_search_results: int = 1000,
    ) -> list[RunFileChange]:
        policy = WorkspacePolicy(
            root=workspace_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )
        snapshots = self._read_command_snapshots(command.id)

        exact_files: list[str] = []
        for task in command.tasks:
            for raw_path in task.exact_files:
                try:
                    resolved = policy.resolve(raw_path, must_exist=False)
                    policy.ensure_not_sensitive(resolved)
                    rel = resolved.relative_to(policy.root).as_posix()
                    if rel not in exact_files:
                        exact_files.append(rel)
                except Exception:
                    continue

        for rel in snapshots:
            if rel not in exact_files:
                exact_files.append(rel)

        terminal_statuses = {"completed", "failed", "cancelled"}
        is_terminal = command.status in terminal_statuses

        changes: list[RunFileChange] = []

        for rel in exact_files:
            snap_info = snapshots.get(rel)
            entry = snap_info["entry"] if snap_info else None
            task_dir = snap_info["task_dir"] if snap_info else None

            existed_before = entry["existed_before"] if entry else False
            sha256_before = entry["sha256_before"] if entry else None
            size_before = entry["size_before"] if entry else None

            before_bytes: bytes | None = None
            if entry and entry.get("blob") and task_dir:
                blob_file = task_dir / entry["blob"]
                if blob_file.is_file():
                    before_bytes = blob_file.read_bytes()

            try:
                disk_path = policy.resolve(rel, must_exist=False)
                policy.ensure_not_sensitive(disk_path)
                disk_exists = disk_path.is_file()
            except Exception:
                disk_exists = False
                disk_path = None

            sha256_after: str | None = None
            size_after: int | None = None
            after_bytes: bytes | None = None
            exists_after = disk_exists

            # Prefer recorded completion snapshot sha256_after if present
            if entry and "sha256_after" in entry and entry["sha256_after"] is not None:
                sha256_after = entry["sha256_after"]
                size_after = entry.get("size_after")
                exists_after = entry.get("exists_after", True)
            elif disk_exists and disk_path:
                try:
                    after_bytes = disk_path.read_bytes()
                    sha256_after = hashlib.sha256(after_bytes).hexdigest()
                    size_after = len(after_bytes)
                except Exception:
                    exists_after = False

            if disk_exists and disk_path and after_bytes is None:
                try:
                    after_bytes = disk_path.read_bytes()
                except Exception:
                    pass

            if not existed_before and not exists_after:
                change_type = "unchanged"
            elif not existed_before and exists_after:
                change_type = "added"
            elif existed_before and not exists_after:
                change_type = "deleted"
            elif sha256_before == sha256_after:
                change_type = "unchanged"
            else:
                change_type = "modified"

            text_diff_preview: str | None = None
            if change_type != "unchanged":
                before_str: str | None = None
                after_str: str | None = None

                if before_bytes is not None:
                    try:
                        before_str = before_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        before_str = None

                if after_bytes is not None:
                    try:
                        after_str = after_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        after_str = None

                is_text = (before_bytes is None or before_str is not None) and (
                    after_bytes is None or after_str is not None
                )

                if is_text and (before_str is not None or after_str is not None):
                    b_lines = (before_str or "").splitlines(keepends=True)
                    a_lines = (after_str or "").splitlines(keepends=True)
                    diff_lines = list(
                        difflib.unified_diff(
                            b_lines,
                            a_lines,
                            fromfile=f"a/{rel}",
                            tofile=f"b/{rel}",
                        )
                    )
                    if diff_lines:
                        diff_text = "".join(diff_lines[:200])
                        if len(diff_text) > 20000:
                            diff_text = diff_text[:20000] + "\n... (diff truncated)"
                        text_diff_preview = diff_text

            revertable = True
            revert_block_reason: str | None = None

            if not is_terminal:
                revertable = False
                revert_block_reason = "Command active / non-terminal"
            elif not snap_info:
                revertable = False
                revert_block_reason = "No initial snapshot available"
            elif change_type == "unchanged":
                revertable = False
                revert_block_reason = "No changes to revert"

            # Check for current disk hash conflict against sha256_after
            if disk_exists and disk_path and sha256_after is not None:
                try:
                    curr_hash = hashlib.sha256(disk_path.read_bytes()).hexdigest()
                    if curr_hash != sha256_after:
                        revertable = False
                        revert_block_reason = "File modified by user after run (hash conflict)"
                except Exception:
                    pass

            changes.append(
                RunFileChange(
                    relative_path=rel,
                    change_type=change_type,
                    existed_before=existed_before,
                    exists_after=exists_after,
                    sha256_before=sha256_before,
                    sha256_after=sha256_after,
                    size_before=size_before,
                    size_after=size_after,
                    text_diff_preview=text_diff_preview,
                    revertable=revertable,
                    revert_block_reason=revert_block_reason,
                )
            )

        return changes

    def revert_command_changes(
        self,
        *,
        command: SupervisorCommand,
        workspace_root: Path,
        confirmation: str,
        max_file_bytes: int = 10_000_000,
        max_search_results: int = 1000,
    ) -> RunRevertResponse:
        expected_confirmation = f"REVERT {command.id}"
        if confirmation.strip() != expected_confirmation:
            raise ValueError(
                f"Confirmation uyuşmuyor. Beklenen format: '{expected_confirmation}'"
            )

        terminal_statuses = {"completed", "failed", "cancelled"}
        if command.status not in terminal_statuses:
            raise ValueError("Revert yalnızca tamamlanmış komutlarda çalışabilir.")

        policy = WorkspacePolicy(
            root=workspace_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )
        snapshots = self._read_command_snapshots(command.id)

        if not snapshots:
            raise ValueError("Bu komut için revert edilecek snapshot bulunamadı.")

        changes = self.build_command_change_review(
            command=command,
            workspace_root=workspace_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )

        reverted: list[str] = []
        skipped: list[str] = []
        conflicts: list[str] = []

        for change in changes:
            rel = change.relative_path
            snap_info = snapshots.get(rel)

            if change.change_type == "unchanged":
                skipped.append(rel)
                continue

            if not snap_info:
                skipped.append(rel)
                continue

            entry = snap_info["entry"]
            task_dir = snap_info["task_dir"]

            try:
                disk_path = policy.resolve(rel, must_exist=False)
                policy.ensure_not_sensitive(disk_path)
            except Exception:
                conflicts.append(rel)
                continue

            # Hash conflict check: only conflict if current hash is neither before_hash nor after_hash
            if disk_path.is_file():
                current_sha256 = hashlib.sha256(disk_path.read_bytes()).hexdigest()
                if current_sha256 == change.sha256_before:
                    # Already in original state
                    skipped.append(rel)
                    continue
                if change.sha256_after and current_sha256 != change.sha256_after:
                    conflicts.append(rel)
                    continue

            if change.change_type in ("modified", "deleted"):
                blob_file = task_dir / entry["blob"] if entry.get("blob") else None
                if blob_file and blob_file.is_file():
                    before_bytes = blob_file.read_bytes()
                    disk_path.parent.mkdir(parents=True, exist_ok=True)
                    disk_path.write_bytes(before_bytes)
                    reverted.append(rel)
                    # Clear recorded sha256_after to reflect restoration
                    entry["sha256_after"] = entry.get("sha256_before")
                    entry["exists_after"] = entry.get("existed_before", True)
                else:
                    conflicts.append(rel)
            elif change.change_type == "added":
                if disk_path.is_file():
                    disk_path.unlink()
                    reverted.append(rel)
                    entry["sha256_after"] = None
                    entry["exists_after"] = False
                else:
                    skipped.append(rel)

        return RunRevertResponse(
            command_id=command.id,
            reverted=reverted,
            skipped=skipped,
            conflicts=conflicts,
            event_recorded=True,
        )
