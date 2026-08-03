from __future__ import annotations

import fnmatch
import json
from pathlib import Path
import subprocess
from typing import Any

from app.core.schemas import (
    WorkspaceProjectGitStatus,
    WorkspaceProjectSelectResponse,
    WorkspaceProjectSummary,
    WorkspaceProjectsResponse,
)
from app.workspace.policy import WorkspacePolicy, ToolError


IGNORE_DIRS = {
    ".git",
    ".github",
    ".adam",
    "data",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "htmlcov",
    ".venv",
    "venv",
    "env",
    ".cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".idea",
    ".vscode",
}

IGNORE_PATTERNS = [
    ".pytest-tmp*",
    ".pytest_tmp*",
]

SENSITIVE_PATTERNS = [
    ".env",
    ".env.*",
    "credentials.json",
    "secrets.yaml",
    "secrets.yml",
    "id_rsa",
    "id_ed25519",
    "*.pem",
    "*.key",
]

MANIFEST_FILES = {
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "Gemfile",
}

SOURCE_DIRS = {"src", "app", "tests", "test"}


class WorkspaceProjectManager:
    def __init__(
        self,
        workspace_root: Path,
        state_root: Path | None = None,
        max_projects: int = 100,
        scan_depth: int = 2,
        max_file_bytes: int = 10_000_000,
        max_search_results: int = 1000,
    ) -> None:
        self.workspace_root = workspace_root.expanduser().resolve()
        self.state_root = (
            state_root.expanduser().resolve()
            if state_root is not None
            else (self.workspace_root / ".adam").resolve()
        )
        self.max_projects = max_projects
        self.scan_depth = scan_depth
        self.policy = WorkspacePolicy(
            root=self.workspace_root,
            max_file_bytes=max_file_bytes,
            max_search_results=max_search_results,
        )
        self.recent_file = self.state_root / "recent_projects.json"

    def _is_ignored_directory(self, rel_path: Path, name: str) -> bool:
        if name in IGNORE_DIRS:
            return True
        for pattern in IGNORE_PATTERNS:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    def _detect_manifests(self, path: Path) -> list[str]:
        found: list[str] = []
        if not path.is_dir():
            return found

        try:
            for item in sorted(path.iterdir()):
                if item.is_file():
                    name = item.name
                    if name in MANIFEST_FILES:
                        found.append(name)
                    elif name.endswith(".sln") or name.endswith(".csproj"):
                        found.append(name)
        except Exception:
            pass

        return found

    def _is_project_candidate(self, path: Path) -> tuple[bool, list[str]]:
        manifests = self._detect_manifests(path)
        if manifests:
            return True, manifests

        if path.is_dir():
            try:
                subdirs = {item.name for item in path.iterdir() if item.is_dir()}
                if subdirs & SOURCE_DIRS:
                    return True, []
            except Exception:
                pass

        return False, []

    def _detect_project_types(self, path: Path, manifests: list[str]) -> list[str]:
        types: set[str] = set()

        # Python & FastApi / Django / Flask
        py_manifests = {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"}
        if any(m in py_manifests for m in manifests):
            types.add("python")

        # Check content for FastAPI / Django / Flask / Typescript / React
        pyproject_txt = ""
        reqs_txt = ""
        pkg_json: dict[str, Any] = {}

        p_pyproject = path / "pyproject.toml"
        if p_pyproject.is_file():
            try:
                pyproject_txt = p_pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                pass

        p_reqs = path / "requirements.txt"
        if p_reqs.is_file():
            try:
                reqs_txt = p_reqs.read_text(encoding="utf-8", errors="ignore").lower()
            except Exception:
                pass

        p_pkg = path / "package.json"
        if p_pkg.is_file():
            types.add("node")
            types.add("javascript")
            try:
                pkg_json = json.loads(p_pkg.read_text(encoding="utf-8", errors="ignore"))
            except Exception:
                pass

        combined_py = pyproject_txt + "\n" + reqs_txt
        if "fastapi" in combined_py:
            types.add("python")
            types.add("fastapi")

        if "django" in combined_py or (path / "manage.py").is_file():
            types.add("python")
            types.add("django")

        if "flask" in combined_py:
            types.add("python")
            types.add("flask")

        # FastAPI / Flask source code check if python
        if "python" in types and "fastapi" not in types and "flask" not in types:
            try:
                for py_file in list(path.glob("*.py"))[:5] + list((path / "app").glob("*.py"))[:5]:
                    if py_file.is_file():
                        content = py_file.read_text(encoding="utf-8", errors="ignore")
                        if "from fastapi import" in content or "import fastapi" in content:
                            types.add("fastapi")
                            break
                        if "Flask(" in content:
                            types.add("flask")
                            break
            except Exception:
                pass

        # Node / Frontend / TS
        all_deps: dict[str, Any] = {}
        if pkg_json:
            all_deps.update(pkg_json.get("dependencies", {}))
            all_deps.update(pkg_json.get("devDependencies", {}))

        if "react" in all_deps:
            types.add("react")
        if "next" in all_deps:
            types.add("nextjs")
        if "vue" in all_deps:
            types.add("vue")
        if "svelte" in all_deps:
            types.add("svelte")
        if "typescript" in all_deps or (path / "tsconfig.json").is_file():
            types.add("typescript")

        if "Cargo.toml" in manifests:
            types.add("rust")
        if "go.mod" in manifests:
            types.add("go")
        if any(m in manifests for m in ("pom.xml", "build.gradle", "build.gradle.kts")):
            types.add("java")
        if any(m.endswith(".sln") or m.endswith(".csproj") for m in manifests):
            types.add("dotnet")
        if "composer.json" in manifests:
            types.add("php")
        if "Gemfile" in manifests:
            types.add("ruby")

        if not types:
            return ["unknown"]

        sorted_types = sorted(list(types))
        return sorted_types

    def _suggest_verifications(
        self,
        path: Path,
        manifests: list[str],
        project_types: list[str],
    ) -> list[str]:
        suggestions: list[str] = []

        if "python" in project_types:
            has_tests = (path / "tests").is_dir() or (path / "test").is_dir() or any(path.glob("test_*.py"))
            if has_tests:
                suggestions.append("python -m pytest -q")

            pyproject_txt = ""
            if (path / "pyproject.toml").is_file():
                try:
                    pyproject_txt = (path / "pyproject.toml").read_text(encoding="utf-8", errors="ignore").lower()
                except Exception:
                    pass

            if "ruff" in pyproject_txt:
                suggestions.append("python -m ruff check .")
            if "mypy" in pyproject_txt:
                suggestions.append("python -m mypy .")

        if "node" in project_types and (path / "package.json").is_file():
            pkg_mgr = "npm"
            if (path / "pnpm-lock.yaml").is_file():
                pkg_mgr = "pnpm"
            elif (path / "yarn.lock").is_file():
                pkg_mgr = "yarn"

            try:
                pkg_data = json.loads((path / "package.json").read_text(encoding="utf-8", errors="ignore"))
                scripts = pkg_data.get("scripts", {})
                if "test" in scripts:
                    suggestions.append(f"{pkg_mgr} test" if pkg_mgr != "npm" else "npm test")
                if "lint" in scripts:
                    suggestions.append(f"{pkg_mgr} run lint")
                if "typecheck" in scripts:
                    suggestions.append(f"{pkg_mgr} run typecheck")
                if "build" in scripts:
                    suggestions.append(f"{pkg_mgr} run build")
            except Exception:
                pass

        if "rust" in project_types:
            suggestions.append("cargo test")
            suggestions.append("cargo check")

        if "go" in project_types:
            suggestions.append("go test ./...")

        if "java" in project_types:
            if (path / "pom.xml").is_file():
                suggestions.append("mvn test")
            if (path / "build.gradle").is_file() or (path / "build.gradle.kts").is_file():
                if (path / "gradlew.bat").is_file():
                    suggestions.append(".\\gradlew.bat test")
                else:
                    suggestions.append("gradle test")

        if "dotnet" in project_types:
            suggestions.append("dotnet test")

        if "php" in project_types and (path / "composer.json").is_file():
            try:
                comp_data = json.loads((path / "composer.json").read_text(encoding="utf-8", errors="ignore"))
                if "test" in comp_data.get("scripts", {}):
                    suggestions.append("composer test")
            except Exception:
                pass

        if "ruby" in project_types and (path / ".rspec").is_file():
            suggestions.append("bundle exec rspec")

        # Unique & stable order, max 8
        unique_suggs: list[str] = []
        for s in suggestions:
            if s not in unique_suggs:
                unique_suggs.append(s)

        return unique_suggs[:8]

    def _read_git_status(self, path: Path) -> WorkspaceProjectGitStatus:
        if not (path / ".git").is_dir() and not (path.parent / ".git").is_dir():
            return WorkspaceProjectGitStatus(is_repository=False)

        try:
            # Check if git repository
            cmd_root = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=2,
            )
            if cmd_root.returncode != 0:
                return WorkspaceProjectGitStatus(is_repository=False)

            git_abs_root = Path(cmd_root.stdout.strip()).resolve()
            try:
                git_rel_root = git_abs_root.relative_to(self.workspace_root).as_posix()
            except ValueError:
                git_rel_root = "."

            # Branch
            cmd_branch = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=2,
            )
            branch = cmd_branch.stdout.strip() if cmd_branch.returncode == 0 else None

            # Status
            cmd_status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(path),
                capture_output=True,
                text=True,
                timeout=2,
            )
            dirty = False
            changed_file_count = 0
            if cmd_status.returncode == 0 and cmd_status.stdout.strip():
                lines = [line for line in cmd_status.stdout.strip().splitlines() if line.strip()]
                changed_file_count = len(lines)
                dirty = changed_file_count > 0

            return WorkspaceProjectGitStatus(
                is_repository=True,
                git_root=git_rel_root,
                branch=branch or "HEAD",
                dirty=dirty,
                changed_file_count=changed_file_count,
            )
        except Exception:
            return WorkspaceProjectGitStatus(is_repository=False)

    def _load_recent_projects(self) -> list[str]:
        if not self.recent_file.is_file():
            return []
        try:
            data = json.loads(self.recent_file.read_text(encoding="utf-8"))
            projects = data.get("projects", [])
            recent_paths: list[str] = []
            for p in projects:
                rel = p.get("workspace_path")
                if rel and isinstance(rel, str) and rel not in recent_paths:
                    recent_paths.append(rel)
            return recent_paths[:10]
        except Exception:
            return []

    def _save_recent_projects(self, workspace_path: str) -> None:
        recents = self._load_recent_projects()
        if workspace_path in recents:
            recents.remove(workspace_path)
        recents.insert(0, workspace_path)
        recents = recents[:10]

        data = {
            "version": 1,
            "projects": [{"workspace_path": p} for p in recents],
        }

        try:
            self.state_root.mkdir(parents=True, exist_ok=True)
            self.recent_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def list_projects(self) -> WorkspaceProjectsResponse:
        recent_paths = self._load_recent_projects()
        recent_map = {path: idx + 1 for idx, path in enumerate(recent_paths)}

        candidate_dirs: list[Path] = [self.workspace_root]

        # Depth 1 and Depth 2 directory traversal
        try:
            for item1 in sorted(self.workspace_root.iterdir()):
                if item1.is_dir():
                    try:
                        resolved1 = self.policy.resolve(item1.relative_to(self.workspace_root).as_posix(), must_exist=True)
                        self.policy.ensure_not_sensitive(resolved1)
                        rel1 = resolved1.relative_to(self.workspace_root)
                        if not self._is_ignored_directory(rel1, resolved1.name):
                            candidate_dirs.append(resolved1)

                            # Depth 2
                            for item2 in sorted(resolved1.iterdir()):
                                if item2.is_dir():
                                    try:
                                        resolved2 = self.policy.resolve(item2.relative_to(self.workspace_root).as_posix(), must_exist=True)
                                        self.policy.ensure_not_sensitive(resolved2)
                                        rel2 = resolved2.relative_to(self.workspace_root)
                                        if not self._is_ignored_directory(rel2, resolved2.name):
                                            candidate_dirs.append(resolved2)
                                    except (ToolError, ValueError, OSError):
                                        continue
                    except (ToolError, ValueError, OSError):
                        continue
        except Exception:
            pass

        summaries: list[WorkspaceProjectSummary] = []

        for candidate in candidate_dirs:
            is_proj, manifests = self._is_project_candidate(candidate)
            if not is_proj:
                continue

            try:
                rel_path = candidate.relative_to(self.workspace_root).as_posix()
            except ValueError:
                rel_path = "."

            if rel_path == "":
                rel_path = "."

            name = candidate.name if rel_path != "." else self.workspace_root.name
            project_types = self._detect_project_types(candidate, manifests)
            suggested_verifications = self._suggest_verifications(candidate, manifests, project_types)
            git_status = self._read_git_status(candidate)
            recent_rank = recent_map.get(rel_path)

            summaries.append(
                WorkspaceProjectSummary(
                    name=name,
                    workspace_path=rel_path,
                    project_types=project_types,
                    manifests=manifests,
                    suggested_verifications=suggested_verifications,
                    git=git_status,
                    recent_rank=recent_rank,
                )
            )

        # Sort: Recent first (by rank), then "." (workspace root), then alphabetically by name
        def sort_key(s: WorkspaceProjectSummary):
            rank = s.recent_rank if s.recent_rank is not None else 999
            is_root = 0 if s.workspace_path == "." else 1
            return (rank, is_root, s.name.lower())

        summaries.sort(key=sort_key)

        total = len(summaries)
        truncated = total > self.max_projects
        final_list = summaries[: self.max_projects]

        return WorkspaceProjectsResponse(
            workspace_root_name=self.workspace_root.name,
            projects=final_list,
            total=total,
            scan_depth=self.scan_depth,
            truncated=truncated,
        )

    def select_project(self, workspace_path: str) -> WorkspaceProjectSelectResponse:
        clean_path = workspace_path.strip() if workspace_path else "."
        if not clean_path:
            clean_path = "."

        try:
            resolved = self.policy.resolve(clean_path, must_exist=True)
            self.policy.ensure_not_sensitive(resolved)
        except (ToolError, ValueError, OSError) as exc:
            raise ValueError(f"Geçersiz veya engellenmiş proje yolu '{workspace_path}': {exc}") from exc

        if not resolved.is_dir():
            raise ValueError(f"Proje yolu bir klasör olmalıdır: '{workspace_path}'")

        is_proj, manifests = self._is_project_candidate(resolved)
        if not is_proj and resolved != self.workspace_root:
            raise ValueError(f"Seçilen klasör geçerli bir proje adayı değil: '{workspace_path}'")

        try:
            rel_path = resolved.relative_to(self.workspace_root).as_posix()
        except ValueError:
            rel_path = "."

        if rel_path == "":
            rel_path = "."

        name = resolved.name if rel_path != "." else self.workspace_root.name
        project_types = self._detect_project_types(resolved, manifests)
        suggested_verifications = self._suggest_verifications(resolved, manifests, project_types)
        git_status = self._read_git_status(resolved)

        self._save_recent_projects(rel_path)

        recent_paths = self._load_recent_projects()
        recent_rank = recent_paths.index(rel_path) + 1 if rel_path in recent_paths else 1

        summary = WorkspaceProjectSummary(
            name=name,
            workspace_path=rel_path,
            project_types=project_types,
            manifests=manifests,
            suggested_verifications=suggested_verifications,
            git=git_status,
            recent_rank=recent_rank,
        )

        return WorkspaceProjectSelectResponse(project=summary, selected=True)
