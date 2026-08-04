from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from app.core.schemas import ProjectRunGitStatus
from app.supervisor.models import SupervisorCommand
from app.workspace.policy import WorkspacePolicy, ToolError


class GitRunManager:
    def __init__(
        self,
        workspace_root: Path,
        max_file_bytes: int = 10_000_000,
        max_search_results: int = 1000,
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.policy = WorkspacePolicy(
            root=self.workspace_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )

    def _run_git(self, cwd: Path, args: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _validate_branch_name(self, name: str) -> None:
        bn = name.strip()
        if not bn:
            raise ValueError("Branch adı boş olamaz.")
        if len(bn) > 120:
            raise ValueError("Branch adı en fazla 120 karakter olabilir.")
        forbidden = ["refs/", "..", "~", "^", ":", "?", "*", "[", "\\"]
        if any(f in bn for f in forbidden):
            raise ValueError(f"Branch adı geçersiz karakterler içeriyor: '{bn}'")
        if bn.startswith("/") or bn.endswith("/") or bn.startswith(".") or bn.endswith("."):
            raise ValueError("Branch adı '/' veya '.' ile başlayamaz/bitemez.")
        if "//" in bn or bn.endswith(".lock"):
            raise ValueError("Branch adı ardışık '//' veya '.lock' son eki içeremez.")

    def inspect_project(
        self,
        *,
        workspace_path: str,
        requested_branch_name: str | None,
        goal: str,
        seed_hash: str | None = None,
    ) -> ProjectRunGitStatus:
        clean_path = workspace_path.strip() if workspace_path else "."
        if not clean_path:
            clean_path = "."

        try:
            target_dir = self.policy.resolve(clean_path, must_exist=True)
            self.policy.ensure_not_sensitive(target_dir)
        except (ToolError, ValueError, OSError) as exc:
            raise ValueError(f"Geçersiz proje yolu '{workspace_path}': {exc}") from exc

        # Check git repo
        res_toplevel = self._run_git(target_dir, ["rev-parse", "--show-toplevel"])
        if res_toplevel.returncode != 0:
            return ProjectRunGitStatus(
                execution_mode="workspace",
                is_repository=False,
            )

        raw_top = res_toplevel.stdout.strip()
        if raw_top.startswith("/") and len(raw_top) > 2 and raw_top[2] == "/":
            raw_top = f"{raw_top[1].upper()}:{raw_top[2:]}"
        
        git_root = Path(raw_top).resolve()
        git_real = os.path.normcase(os.path.normpath(os.path.realpath(raw_top)))
        ws_real = os.path.normcase(os.path.normpath(os.path.realpath(str(self.policy.root))))

        sep = os.sep
        ws_prefix = ws_real if ws_real.endswith(sep) else ws_real + sep
        git_prefix = git_real if git_real.endswith(sep) else git_real + sep

        # If git_real is strictly an ancestor of ws_real (i.e. repo root is outside/above workspace root)
        if ws_prefix.startswith(git_prefix) and git_real != ws_real:
            raise ValueError("Git repository'si verilen workspace root sınırlarının dışında.")

        # Current branch
        res_branch = self._run_git(target_dir, ["branch", "--show-current"])
        base_branch = res_branch.stdout.strip()
        if not base_branch:
            raise ValueError("Git repository Detached HEAD durumunda, isolated branch çalıştırılamaz.")

        # Current HEAD
        res_head = self._run_git(target_dir, ["rev-parse", "HEAD"])
        if res_head.returncode != 0:
            raise ValueError("Git HEAD commit okunamadı.")
        base_head = res_head.stdout.strip()

        # Check worktree clean
        res_status = self._run_git(target_dir, ["status", "--porcelain"])
        dirty_lines = [l for l in res_status.stdout.strip().splitlines() if l.strip()]
        worktree_clean = len(dirty_lines) == 0
        if not worktree_clean:
            raise ValueError("Git çalışma dizininde kaydedilmemiş değişiklikler var. Lütfen önce commit/stash yapın.")

        # Check in-progress operation states
        git_dir = git_root / ".git"
        if (git_dir / "MERGE_HEAD").exists() or (git_dir / "REBASE_HEAD").exists() or (git_dir / "CHERRY_PICK_HEAD").exists():
            raise ValueError("Git repository'sinde tamamlanmamış bir merge/rebase/cherry-pick işlemi var.")

        # Determine run branch name
        if requested_branch_name:
            self._validate_branch_name(requested_branch_name)
            run_branch = requested_branch_name.strip()
        else:
            if seed_hash:
                short_hash = seed_hash[:12]
            else:
                raw_seed = f"{clean_path}:{goal}:{base_branch}:{base_head}"
                short_hash = hashlib.sha256(raw_seed.encode("utf-8")).hexdigest()[:12]
            run_branch = f"prometheus/run-{short_hash}"

        # Check if run_branch already exists
        res_check_branch = self._run_git(target_dir, ["rev-parse", "--verify", f"refs/heads/{run_branch}"])
        if res_check_branch.returncode == 0:
            raise ValueError(f"Önerilen veya istenen '{run_branch}' branch'i zaten mevcut.")

        return ProjectRunGitStatus(
            execution_mode="isolated_branch",
            is_repository=True,
            base_branch=base_branch,
            base_head=base_head,
            run_branch=run_branch,
            branch_created=False,
            current_branch=base_branch,
            worktree_clean=True,
            commit_created=False,
            commit_hash=None,
        )

    def prepare_run_branch(
        self,
        *,
        command: SupervisorCommand,
    ) -> ProjectRunGitStatus:
        if command.project_run_execution_mode != "isolated_branch":
            return ProjectRunGitStatus(execution_mode="workspace", is_repository=False)

        run_branch = command.project_run_git_branch_name
        base_branch = command.project_run_git_base_branch
        base_head = command.project_run_git_base_head

        if not run_branch or not base_branch or not base_head:
            raise ValueError("Command içinde eksik Git-isolated metadata'sı var.")

        ws_path = command.project_run_workspace_path or "."
        target_dir = self.policy.resolve(ws_path, must_exist=True)

        res_curr = self._run_git(target_dir, ["branch", "--show-current"])
        current_branch = res_curr.stdout.strip()

        # If already created
        if command.project_run_git_branch_created:
            if current_branch != run_branch:
                # Switch to run_branch if worktree clean
                res_st = self._run_git(target_dir, ["status", "--porcelain"])
                if res_st.stdout.strip():
                    raise ValueError(f"Run branch '{run_branch}' üzerine geçilemedi: worktree kirli.")
                res_sw = self._run_git(target_dir, ["switch", run_branch])
                if res_sw.returncode != 0:
                    raise ValueError(f"Run branch '{run_branch}' üzerine geçilemedi: {res_sw.stderr}")
                current_branch = run_branch

            return ProjectRunGitStatus(
                execution_mode="isolated_branch",
                is_repository=True,
                base_branch=base_branch,
                base_head=base_head,
                run_branch=run_branch,
                branch_created=True,
                current_branch=current_branch,
                worktree_clean=True,
                commit_created=command.project_run_git_commit_hash is not None,
                commit_hash=command.project_run_git_commit_hash,
            )

        # Pre-checks before branch creation
        res_st = self._run_git(target_dir, ["status", "--porcelain"])
        if res_st.stdout.strip():
            raise ValueError("Branch oluşturulamadı: Git çalışma alanı kirli.")

        res_head = self._run_git(target_dir, ["rev-parse", "HEAD"])
        if res_head.returncode != 0 or res_head.stdout.strip() != base_head:
            raise ValueError(f"Git HEAD değişmiş (beklenen: {base_head[:8]}, mevcut: {res_head.stdout.strip()[:8]}).")

        # Create branch & switch
        res_create = self._run_git(target_dir, ["switch", "-c", run_branch, base_head])
        if res_create.returncode != 0:
            raise ValueError(f"Git branch '{run_branch}' oluşturulamadı: {res_create.stderr}")

        command.project_run_git_branch_created = True

        return ProjectRunGitStatus(
            execution_mode="isolated_branch",
            is_repository=True,
            base_branch=base_branch,
            base_head=base_head,
            run_branch=run_branch,
            branch_created=True,
            current_branch=run_branch,
            worktree_clean=True,
            commit_created=False,
            commit_hash=None,
        )

    def finalize_successful_run(
        self,
        *,
        command: SupervisorCommand,
    ) -> ProjectRunGitStatus:
        if command.project_run_execution_mode != "isolated_branch":
            return ProjectRunGitStatus(execution_mode="workspace", is_repository=False)

        run_branch = command.project_run_git_branch_name
        base_branch = command.project_run_git_base_branch
        base_head = command.project_run_git_base_head

        if command.project_run_git_commit_hash:
            return ProjectRunGitStatus(
                execution_mode="isolated_branch",
                is_repository=True,
                base_branch=base_branch,
                base_head=base_head,
                run_branch=run_branch,
                branch_created=True,
                current_branch=run_branch,
                commit_created=True,
                commit_hash=command.project_run_git_commit_hash,
                commit_message=command.project_run_git_commit_message,
            )

        ws_path = command.project_run_workspace_path or "."
        target_dir = self.policy.resolve(ws_path, must_exist=True)

        # Collect exact files scope
        exact_files_set: set[str] = set()
        for t in command.tasks:
            if t.exact_files:
                for ef in t.exact_files:
                    if ef and ef.strip():
                        exact_files_set.add(ef.strip())

        if not exact_files_set:
            return ProjectRunGitStatus(
                execution_mode="isolated_branch",
                is_repository=True,
                base_branch=base_branch,
                base_head=base_head,
                run_branch=run_branch,
                branch_created=True,
                current_branch=run_branch,
                commit_created=False,
            )

        # Stage exact files ONLY
        staged_paths: list[str] = []
        for ef in sorted(list(exact_files_set)):
            try:
                resolved_ef = self.policy.resolve(ef, must_exist=False)
                self.policy.ensure_not_sensitive(resolved_ef)
                rel_posix = resolved_ef.relative_to(self.workspace_root).as_posix()
                staged_paths.append(rel_posix)
            except Exception:
                continue

        if not staged_paths:
            return ProjectRunGitStatus(
                execution_mode="isolated_branch",
                is_repository=True,
                base_branch=base_branch,
                base_head=base_head,
                run_branch=run_branch,
                branch_created=True,
                current_branch=run_branch,
                commit_created=False,
            )

        # Check out-of-scope dirty files
        res_status = self._run_git(target_dir, ["status", "--porcelain"])
        dirty_lines = [l.strip() for l in res_status.stdout.strip().splitlines() if l.strip()]
        out_of_scope_dirty = False
        for line in dirty_lines:
            # line format: " M path" or "?? path"
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                file_path = parts[1].strip()
                if file_path not in staged_paths:
                    out_of_scope_dirty = True
                    break

        if out_of_scope_dirty:
            # Out of scope dirty files present -> skip auto commit safely
            return ProjectRunGitStatus(
                execution_mode="isolated_branch",
                is_repository=True,
                base_branch=base_branch,
                base_head=base_head,
                run_branch=run_branch,
                branch_created=True,
                current_branch=run_branch,
                commit_created=False,
            )

        # Stage exact files
        res_add = self._run_git(target_dir, ["add", "--"] + staged_paths)
        if res_add.returncode != 0:
            return ProjectRunGitStatus(
                execution_mode="isolated_branch",
                is_repository=True,
                base_branch=base_branch,
                base_head=base_head,
                run_branch=run_branch,
                branch_created=True,
                current_branch=run_branch,
                commit_created=False,
            )

        # Check if anything is staged
        res_diff = self._run_git(target_dir, ["diff", "--staged", "--quiet"])
        if res_diff.returncode == 0:
            # Nothing staged to commit
            return ProjectRunGitStatus(
                execution_mode="isolated_branch",
                is_repository=True,
                base_branch=base_branch,
                base_head=base_head,
                run_branch=run_branch,
                branch_created=True,
                current_branch=run_branch,
                commit_created=False,
            )

        # Build commit message
        goal_summary = command.goal.replace("\n", " ").strip()
        if len(goal_summary) > 50:
            goal_summary = goal_summary[:47] + "..."
        subject = f"Prometheus run {command.id[:8]}: {goal_summary}"
        body = f"Command: {command.id}\nPreview: {command.project_run_preview_digest or 'none'}"

        res_commit = self._run_git(target_dir, ["commit", "-m", subject, "-m", body])
        if res_commit.returncode != 0:
            # Commit failed (e.g. user git identity missing), do not break run success
            return ProjectRunGitStatus(
                execution_mode="isolated_branch",
                is_repository=True,
                base_branch=base_branch,
                base_head=base_head,
                run_branch=run_branch,
                branch_created=True,
                current_branch=run_branch,
                commit_created=False,
            )

        res_hash = self._run_git(target_dir, ["rev-parse", "HEAD"])
        commit_hash = res_hash.stdout.strip() if res_hash.returncode == 0 else None

        command.project_run_git_commit_hash = commit_hash
        command.project_run_git_commit_message = subject

        return ProjectRunGitStatus(
            execution_mode="isolated_branch",
            is_repository=True,
            base_branch=base_branch,
            base_head=base_head,
            run_branch=run_branch,
            branch_created=True,
            current_branch=run_branch,
            commit_created=True,
            commit_hash=commit_hash,
            commit_message=subject,
        )

    def get_status(
        self,
        *,
        command: SupervisorCommand,
    ) -> ProjectRunGitStatus:
        if command.project_run_execution_mode != "isolated_branch":
            return ProjectRunGitStatus(
                execution_mode="workspace",
                is_repository=False,
            )

        ws_path = command.project_run_workspace_path or "."
        target_dir = self.policy.resolve(ws_path, must_exist=False)

        current_branch = None
        worktree_clean = None
        if target_dir.is_dir():
            try:
                res_b = self._run_git(target_dir, ["branch", "--show-current"])
                if res_b.returncode == 0:
                    current_branch = res_b.stdout.strip()
                res_st = self._run_git(target_dir, ["status", "--porcelain"])
                if res_st.returncode == 0:
                    worktree_clean = len(res_st.stdout.strip().splitlines()) == 0
            except Exception:
                pass

        return ProjectRunGitStatus(
            execution_mode="isolated_branch",
            is_repository=True,
            base_branch=command.project_run_git_base_branch,
            base_head=command.project_run_git_base_head,
            run_branch=command.project_run_git_branch_name,
            branch_created=command.project_run_git_branch_created,
            current_branch=current_branch,
            worktree_clean=worktree_clean,
            commit_created=command.project_run_git_commit_hash is not None,
            commit_hash=command.project_run_git_commit_hash,
            commit_message=command.project_run_git_commit_message,
        )
