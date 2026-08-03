from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from app.tools.base import BaseTool, ToolError
from app.workspace.policy import WorkspacePolicy


TERMINAL_RUNTIME_REVISION = "terminal-env-v8-pytest-isolated"


class SafeTerminalTool(BaseTool):
    name = "safe_terminal"
    description = (
        "Yalnızca önceden tanımlı test, build, statik analiz ve açıkça "
        "onaylanan araç zinciri kurulumlarını workspace kökünde çalıştırır."
    )
    risk_level = "execute"
    requires_approval = True
    approval_description = (
        "Proje kodu, build aracı veya açıkça gösterilen araç zinciri "
        "işlemi yerel bilgisayarda çalıştırılacak."
    )
    parameters = {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": [
                    "python_compile",
                    "pytest",
                    "flutter_analyze",
                    "flutter_test",
                    "npm_install",
                    "npm_install_dev",
                    "npm_test",
                    "npm_build",
                    "node_test",
                    "node_check",
                    "file_exists",
                    "install_node_lts",
                    "pip_install_dev",
                    "gradle_test",
                ],
            },
            "extra_args": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 20,
            },
        },
        "required": ["preset"],
        "additionalProperties": False,
    }

    runtime_revision = TERMINAL_RUNTIME_REVISION

    def __init__(
        self,
        *,
        workspace: WorkspacePolicy,
        timeout_seconds: int,
        max_output_chars: int,
    ) -> None:
        self.workspace = workspace
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars

    @staticmethod
    def _candidate_directories() -> list[Path]:
        values: list[Path] = []

        def add(value: str | None) -> None:
            if not value:
                return
            path = Path(value).expanduser()
            if path not in values:
                values.append(path)

        for item in os.environ.get("PATH", "").split(os.pathsep):
            add(item)

        program_files = os.environ.get("ProgramFiles")
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        local_app_data = os.environ.get("LOCALAPPDATA")
        app_data = os.environ.get("APPDATA")
        user_profile = os.environ.get("USERPROFILE")
        volta_home = os.environ.get("VOLTA_HOME")

        if program_files:
            add(str(Path(program_files) / "nodejs"))
        if program_files_x86:
            add(str(Path(program_files_x86) / "nodejs"))
        if local_app_data:
            add(str(Path(local_app_data) / "Programs" / "nodejs"))
        if app_data:
            add(str(Path(app_data) / "npm"))
        if user_profile:
            profile = Path(user_profile)
            add(str(profile / "scoop" / "shims"))
            add(str(profile / "scoop" / "apps" / "nodejs" / "current"))
            add(str(profile / ".volta" / "bin"))
        if volta_home:
            add(str(Path(volta_home) / "bin"))

        add(os.environ.get("NVM_HOME"))
        add(os.environ.get("NVM_SYMLINK"))
        return values

    @classmethod
    def _resolve_executable(cls, name: str) -> str | None:
        direct = shutil.which(name)
        if direct:
            return direct

        suffixes = [""]
        if os.name == "nt":
            suffixes = ["", ".exe", ".cmd", ".bat"]

        base = Path(name)
        if base.is_absolute() and base.exists():
            return str(base)

        for directory in cls._candidate_directories():
            for suffix in suffixes:
                candidate = directory / f"{name}{suffix}"
                try:
                    is_file = candidate.is_file()
                except OSError:
                    is_file = False
                if is_file:
                    return str(candidate)
        return None

    @classmethod
    def _resolve_npm_base(cls) -> list[str] | None:
        node = cls._resolve_executable("node")
        npm = cls._resolve_executable("npm")

        npm_cli_candidates: list[Path] = []
        if node:
            node_dir = Path(node).parent
            npm_cli_candidates.extend(
                [
                    node_dir / "node_modules" / "npm" / "bin" / "npm-cli.js",
                    node_dir.parent / "node_modules" / "npm" / "bin" / "npm-cli.js",
                ]
            )

        app_data = os.environ.get("APPDATA")
        if app_data:
            npm_cli_candidates.append(
                Path(app_data) / "npm" / "node_modules" / "npm" / "bin" / "npm-cli.js"
            )

        if npm:
            npm_dir = Path(npm).parent
            npm_cli_candidates.append(
                npm_dir / "node_modules" / "npm" / "bin" / "npm-cli.js"
            )

        if node:
            for candidate in npm_cli_candidates:
                try:
                    is_file = candidate.is_file()
                except OSError:
                    is_file = False
                if is_file:
                    return [node, str(candidate)]

        if npm:
            return [npm]
        return None

    _NPM_PACKAGE_RE = re.compile(
        r"^(?:@[a-z0-9._-]+/[a-z0-9._-]+|[a-z0-9][a-z0-9._-]*)$",
        re.IGNORECASE,
    )
    _JS_TEST_SUFFIXES = (
        ".test.js",
        ".test.jsx",
        ".test.ts",
        ".test.tsx",
        ".spec.js",
        ".spec.jsx",
        ".spec.ts",
        ".spec.tsx",
    )
    _NODE_BUILTINS = {
        "assert", "buffer", "child_process", "crypto", "events", "fs",
        "http", "https", "module", "os", "path", "process", "stream",
        "string_decoder", "timers", "tty", "url", "util", "worker_threads",
        "zlib",
    }

    @classmethod
    def _validated_npm_packages(cls, value: Any) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ToolError("npm_install_dev en az bir paket adı ister.")
        if len(value) > 8:
            raise ToolError("Tek işlemde en fazla 8 npm paketi kurulabilir.")
        packages: list[str] = []
        for raw in value:
            if not isinstance(raw, str):
                raise ToolError("npm paket adları metin olmalıdır.")
            package = raw.strip()
            # Reject shell injection characters
            if any(char in package for char in ("&", ";", "|", "`", "$", "<", ">", "\n", "\r")):
                continue  # silently skip instead of crashing
            # Reject natural language / LLM prose:
            # Real npm names don't contain spaces, parentheses, or Turkish chars
            if any(char in package for char in (" ", "(", ")", "ı", "ş", "ğ", "ü", "ö", "ç", "İ", "Ş")):
                continue  # skip LLM commentary
            # Reject if it looks like a sentence fragment (>40 chars = definitely not a package name)
            if len(package) > 80:
                continue
            if cls._NPM_PACKAGE_RE.fullmatch(package) and package not in packages:
                packages.append(package)
        if not packages:
            raise ToolError("npm_install_dev geçerli bir npm paket adı içermelidir.")
        return packages

    @classmethod
    def _package_root(cls, specifier: str) -> str | None:
        value = specifier.strip()
        if (
            not value
            or value.startswith((".", "/", "node:", "#"))
            or "://" in value
        ):
            return None
        if value.startswith("@"):
            parts = value.split("/")
            root = "/".join(parts[:2]) if len(parts) >= 2 else None
        else:
            root = value.split("/", 1)[0]
        if root and cls._NPM_PACKAGE_RE.fullmatch(root):
            return root
        return None

    def _javascript_test_files(self) -> list[Path]:
        files: list[Path] = []
        for path in self.workspace.root.rglob("*"):
            if len(files) >= 250:
                break
            try:
                if not path.is_file():
                    continue
            except OSError:
                continue
            relative_parts = set(path.relative_to(self.workspace.root).parts)
            if relative_parts & {
                "node_modules", ".git", ".adam", "dist", "build", "coverage"
            }:
                continue
            if path.name.endswith(self._JS_TEST_SUFFIXES):
                files.append(path)
        return files

    @staticmethod
    def _read_small_text(path: Path, max_bytes: int = 300_000) -> str:
        try:
            if path.stat().st_size > max_bytes:
                return ""
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    @classmethod
    def _bare_imports(cls, source: str) -> set[str]:
        values: set[str] = set()
        patterns = (
            r"(?:from\s+|import\s*\()\s*['\"]([^'\"]+)['\"]",
            r"import\s*['\"]([^'\"]+)['\"]",
            r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
        )
        for pattern in patterns:
            for specifier in re.findall(pattern, source):
                root = cls._package_root(specifier)
                if root and root not in cls._NODE_BUILTINS:
                    values.add(root)
        return values

    @staticmethod
    def _package_path(node_modules: Path, package: str) -> Path:
        if package.startswith("@"):
            scope, name = package.split("/", 1)
            return node_modules / scope / name
        return node_modules / package

    @staticmethod
    def _vitest_globals_enabled(root: Path, script: str) -> bool:
        if "--globals" in script:
            return True
        for name in (
            "vitest.config.ts", "vitest.config.js", "vitest.config.mts",
            "vitest.config.mjs", "vite.config.ts", "vite.config.js",
        ):
            path = root / name
            try:
                if not path.is_file():
                    continue
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"\bglobals\s*:\s*true\b", source):
                return True
        return False

    @staticmethod
    def _uses_unimported_vitest_globals(source: str) -> bool:
        if not re.search(
            r"\b(?:describe|it|test|expect|beforeEach|afterEach)\s*\(",
            source,
        ):
            return False
        imports = "\n".join(
            re.findall(
                r"import\s*\{([^}]*)\}\s*from\s*['\"](?:vitest|@jest/globals)['\"]",
                source,
                flags=re.DOTALL,
            )
        )
        imported = {
            item.strip().split(" as ", 1)[0].strip()
            for item in imports.split(",")
            if item.strip()
        }
        used = set(
            re.findall(
                r"\b(describe|it|test|expect|beforeEach|afterEach)\s*\(",
                source,
            )
        )
        return bool(used - imported)

    @staticmethod
    def _normalize_extra(extra_args: Any, command: list[str]) -> list[str]:
        if not isinstance(extra_args, list) or not all(
            isinstance(item, str) for item in extra_args
        ):
            raise ToolError("'extra_args' metin listesi olmalıdır.")
        if len(extra_args) > 20:
            raise ToolError("Çok fazla ek argüman.")

        normalized: list[str] = []
        for item in extra_args:
            if item.startswith("-") and item in command:
                continue
            if item not in normalized:
                normalized.append(item)
        return normalized

    def _pytest_config_argument(self) -> str:
        candidates = (
            ("pytest.ini", None),
            (".pytest.ini", None),
            ("pyproject.toml", "[tool.pytest.ini_options]"),
            ("tox.ini", "[pytest]"),
            ("setup.cfg", "[tool:pytest]"),
        )
        for name, marker in candidates:
            path = self.workspace.root / name
            if not path.is_file():
                continue
            if marker is None:
                return name
            try:
                content = path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            except OSError:
                continue
            if marker in content:
                return name
        return os.devnull

    def _resolved_command(
        self,
        arguments: dict[str, Any],
    ) -> tuple[list[str] | None, str | None, list[str]]:
        preset = str(arguments.get("preset", "")).strip()
        extra_args = arguments.get("extra_args", [])

        logical: list[str]
        command: list[str] | None
        missing: str | None = None

        if preset == "python_compile":
            logical = ["python", "-m", "compileall", "-q", "."]
            command = [sys.executable, "-m", "compileall", "-q", "."]
        elif preset == "file_exists":
            paths = self._validated_workspace_files(extra_args, maximum=20)
            script = (
                "from pathlib import Path; import sys; "
                "missing=[p for p in sys.argv[1:] if not Path(p).is_file() or Path(p).stat().st_size == 0]; "
                "raise SystemExit(('Eksik veya boş dosya: ' + ', '.join(missing)) if missing else 0)"
            )
            logical = ["python", "-c", "<workspace file check>", *paths]
            command = [sys.executable, "-c", script, *paths]
            extra_args = []
        elif preset in {"node_test", "node_check"}:
            node = self._resolve_executable("node")
            paths = self._validated_node_paths(
                extra_args,
                maximum=20 if preset == "node_test" else 1,
            )
            tail = ["--test", *paths] if preset == "node_test" else [
                "--check",
                *paths,
            ]
            logical = ["node", *tail]
            command = [node, *tail] if node else None
            missing = None if node else "node"
            extra_args = []
        elif preset == "pytest":
            pytest_config = self._pytest_config_argument()
            logical = [
                "python",
                "-m",
                "pytest",
                "-q",
                "-c",
                pytest_config,
                "--rootdir=.",
                "--confcutdir=.",
            ]
            command = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-c",
                pytest_config,
                "--rootdir=.",
                "--confcutdir=.",
            ]
        elif preset in {
            "npm_install",
            "npm_install_dev",
            "npm_test",
            "npm_build",
        }:
            npm_base = self._resolve_npm_base()
            if preset == "npm_install":
                # Repairs absent or partial node_modules trees.
                tail = ["install"]
            elif preset == "npm_install_dev":
                packages = self._validated_npm_packages(extra_args)
                tail = ["install", "--save-dev", *packages]
                extra_args = []
            elif preset == "npm_test":
                tail = ["test", "--"]
            else:
                tail = ["run", "build"]
            logical = ["npm", *tail]
            command = [*npm_base, *tail] if npm_base else None
            if command is None:
                missing = "npm"
        elif preset == "install_node_lts":
            logical = ["winget", "install", "--id", "OpenJS.NodeJS.LTS", "--exact"]
            winget = self._resolve_executable("winget")
            if os.name != "nt":
                command = None
                missing = "node_installer"
            elif winget is None:
                command = None
                missing = "winget"
            else:
                command = [
                    winget,
                    "install",
                    "--id",
                    "OpenJS.NodeJS.LTS",
                    "--exact",
                    "--accept-package-agreements",
                    "--accept-source-agreements",
                    "--silent",
                ]
        elif preset in {"flutter_analyze", "flutter_test"}:
            tail = ["analyze"] if preset == "flutter_analyze" else ["test"]
            logical = ["flutter", *tail]
            flutter = self._resolve_executable("flutter")
            command = [flutter, *tail] if flutter else None
            if command is None:
                missing = "flutter"
        elif preset == "pip_install_dev":
            logical = ["python", "-m", "pip", "install", "-r", "requirements-dev.txt"]
            command = [sys.executable, "-m", "pip", "install", "-r", "requirements-dev.txt"]
        elif preset == "gradle_test":
            wrapper_name = "gradlew.bat" if os.name == "nt" else "gradlew"
            wrapper = self.workspace.root / wrapper_name
            logical = [wrapper_name, "test"]
            command = [str(wrapper), "test"] if wrapper.is_file() else None
            if command is None:
                missing = wrapper_name
        else:
            raise ToolError("Bilinmeyen terminal preset'i.")

        base = command if command is not None else logical
        normalized_extra = self._normalize_extra(extra_args, base)
        logical = [*logical, *normalized_extra]
        if command is not None:
            command = [*command, *normalized_extra]
        return command, missing, logical

    def _validated_workspace_files(
        self,
        value: Any,
        *,
        maximum: int,
    ) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ToolError("Dosya doğrulaması en az bir workspace dosyası ister.")
        if len(value) > maximum:
            raise ToolError(f"Dosya doğrulamasında en fazla {maximum} dosya kullanılabilir.")
        root = self.workspace.root.resolve()
        paths: list[str] = []
        for raw in value:
            if not isinstance(raw, str) or not raw.strip():
                raise ToolError("Doğrulama yolu metin olmalı.")
            relative = Path(raw.strip())
            target = (root / relative).resolve()
            if relative.is_absolute() or ".." in relative.parts or root not in target.parents:
                raise ToolError(f"Güvensiz dosya doğrulama yolu: {raw}")
            normalized = relative.as_posix()
            if normalized not in paths:
                paths.append(normalized)
        return paths

    def _validated_node_paths(
        self,
        value: Any,
        *,
        maximum: int,
    ) -> list[str]:
        if not isinstance(value, list) or not value:
            raise ToolError("Node doğrulaması en az bir workspace dosyası ister.")
        if len(value) > maximum:
            raise ToolError(
                f"Node doğrulamasında en fazla {maximum} dosya kullanılabilir."
            )
        root = self.workspace.root.resolve()
        paths: list[str] = []
        allowed_suffixes = {".js", ".mjs", ".cjs", ".ts"}
        _VITEST_FLAGS = {"--run", "--globals", "--environment", "--coverage", "--ui"}
        for raw in value:
            if not isinstance(raw, str) or not raw.strip():
                raise ToolError("Node doğrulama yolu metin olmalı.")
            item = raw.strip()
            if item in _VITEST_FLAGS or item.startswith(("--reporter", "--environment=")):
                continue
            relative = Path(item)
            if relative.is_absolute() or ".." in relative.parts:
                raise ToolError(f"Güvensiz Node doğrulama yolu: {raw}")
            target = (root / relative).resolve()
            if root not in target.parents or target.suffix.casefold() not in (
                allowed_suffixes
            ):
                raise ToolError(f"Workspace dışı veya desteklenmeyen yol: {raw}")
            normalized = relative.as_posix()
            if normalized not in paths:
                paths.append(normalized)
        if not paths:
            paths.append(".")
        return paths

    def _execution_environment(
        self,
        command: list[str],
    ) -> tuple[dict[str, str], list[str]]:
        env = dict(os.environ)
        candidates: list[str] = []

        def add(path: Path | str | None) -> None:
            if not path:
                return
            candidate = Path(path)
            try:
                if candidate.is_file():
                    candidate = candidate.parent
            except OSError:
                # An unreadable PATH entry must never abort a safe command.
                return
            text = str(candidate)
            if text and text not in candidates:
                candidates.append(text)

        # Absolute executable and script paths used by the command must also
        # be visible to lifecycle scripts spawned by npm/esbuild.
        for item in command:
            path = Path(item)
            if path.is_absolute():
                add(path)

        node = self._resolve_executable("node")
        if node:
            add(node)
        npm_base = self._resolve_npm_base() or []
        for item in npm_base:
            add(Path(item))
        for directory in self._candidate_directories():
            add(directory)

        for item in env.get("PATH", "").split(os.pathsep):
            if item and item not in candidates:
                candidates.append(item)

        env["PATH"] = os.pathsep.join(candidates)
        env["PROMETHEUS_TERMINAL_RUNTIME_REVISION"] = TERMINAL_RUNTIME_REVISION
        # Compatibility for tasks and scripts created before the rebrand.
        env["ADAM_TERMINAL_RUNTIME_REVISION"] = TERMINAL_RUNTIME_REVISION
        if os.name == "nt":
            env.setdefault("PATHEXT", ".COM;.EXE;.BAT;.CMD")
        return env, candidates

    def _timeout_for_preset(self, preset: str) -> int:
        if preset in {
            "install_node_lts",
            "npm_install",
            "npm_install_dev",
            "pip_install_dev",
        }:
            return max(self.timeout_seconds, 900)
        if preset in {"npm_build", "gradle_test", "flutter_test"}:
            return max(self.timeout_seconds, 300)
        return self.timeout_seconds

    async def preflight(self, arguments: dict[str, Any]) -> dict[str, Any]:
        preset = str(arguments.get("preset", "")).strip()
        command, missing, logical = self._resolved_command(arguments)
        if command is None:
            remediation = None
            if missing == "npm":
                remediation = {
                    "tool": "safe_terminal",
                    "arguments": {"preset": "install_node_lts", "extra_args": []},
                    "requires_explicit_approval": True,
                }
            return {
                "ready": False,
                "failure_kind": "missing_command",
                "missing_command": missing,
                "logical_command": logical,
                "remediation": remediation,
                "runtime_revision": TERMINAL_RUNTIME_REVISION,
            }

        if preset in {"npm_test", "npm_build"}:
            package_json = self.workspace.root / "package.json"
            if not package_json.is_file():
                return {
                    "ready": False,
                    "failure_kind": "missing_package_manifest",
                    "message": "package.json bulunamadı.",
                    "suggested_files": ["package.json"],
                    "runtime_revision": TERMINAL_RUNTIME_REVISION,
                }
            try:
                manifest = json.loads(package_json.read_text(encoding="utf-8"))
            except Exception as exc:
                return {
                    "ready": False,
                    "failure_kind": "invalid_package_manifest",
                    "message": f"package.json okunamadı: {type(exc).__name__}: {exc}",
                    "suggested_files": ["package.json"],
                    "runtime_revision": TERMINAL_RUNTIME_REVISION,
                }

            script_name = "test" if preset == "npm_test" else "build"
            scripts = manifest.get("scripts") if isinstance(manifest, dict) else None
            script = scripts.get(script_name) if isinstance(scripts, dict) else None
            if not isinstance(script, str) or not script.strip():
                return {
                    "ready": False,
                    "failure_kind": "missing_npm_script",
                    "message": f"package.json içinde '{script_name}' scripti bulunamadı.",
                    "suggested_files": ["package.json"],
                    "runtime_revision": TERMINAL_RUNTIME_REVISION,
                }

            node_modules = self.workspace.root / "node_modules"
            bin_dir = node_modules / ".bin"
            normalized_script = script.casefold()
            declared: set[str] = set()
            for key in (
                "dependencies",
                "devDependencies",
                "optionalDependencies",
                "peerDependencies",
            ):
                values = (
                    manifest.get(key)
                    if isinstance(manifest, dict)
                    else None
                )
                if isinstance(values, dict):
                    declared.update(str(item) for item in values)

            package_runners = {
                "vitest",
                "jest",
                "mocha",
                "ava",
                "tap",
                "tsx",
                "ts-node",
                "vite",
                "webpack",
            }
            invokes_package_runner = any(
                re.search(
                    rf"(^|[\s;&|]){re.escape(runner)}(?:[\s;&|]|$)",
                    normalized_script,
                )
                for runner in package_runners
            )
            # A package with no declared dependencies can legitimately use
            # Node's built-in test runner without a node_modules directory.
            needs_install = (
                not node_modules.is_dir()
                and (bool(declared) or invokes_package_runner)
            )
            if "vitest" in normalized_script:
                vitest_names = ["vitest", "vitest.cmd", "vitest.exe"]
                needs_install = needs_install or not any((bin_dir / name).is_file() for name in vitest_names)

            if needs_install:
                return {
                    "ready": False,
                    "failure_kind": "npm_dependencies_not_installed",
                    "message": "Node bağımlılıkları kurulmamış veya eksik.",
                    "remediation": {
                        "tool": "safe_terminal",
                        "arguments": {"preset": "npm_install", "extra_args": []},
                        "requires_explicit_approval": True,
                    },
                    "runtime_revision": TERMINAL_RUNTIME_REVISION,
                }

            if preset == "npm_test":
                test_files = self._javascript_test_files()
                sources = [self._read_small_text(path) for path in test_files]
                imports: set[str] = set()
                for source in sources:
                    imports.update(self._bare_imports(source))

                node_modules = self.workspace.root / "node_modules"
                missing_packages = sorted(
                    package
                    for package in imports
                    if package not in {"vitest"}
                    and not self._package_path(node_modules, package).is_dir()
                    and package not in declared
                )
                if missing_packages:
                    return {
                        "ready": False,
                        "failure_kind": "npm_test_packages_missing",
                        "message": (
                            "Test dosyalarının içe aktardığı geliştirme "
                            "paketleri eksik: " + ", ".join(missing_packages)
                        ),
                        "missing_packages": missing_packages,
                        "remediation": {
                            "tool": "safe_terminal",
                            "arguments": {
                                "preset": "npm_install_dev",
                                "extra_args": missing_packages[:8],
                            },
                            "requires_explicit_approval": True,
                        },
                        "runtime_revision": TERMINAL_RUNTIME_REVISION,
                    }

                raw_extra = arguments.get("extra_args", [])
                if not isinstance(raw_extra, list) or not all(
                    isinstance(item, str) for item in raw_extra
                ):
                    raise ToolError("'extra_args' metin listesi olmalıdır.")
                extra = list(dict.fromkeys(raw_extra))
                uses_vitest = (
                    "vitest" in normalized_script
                    or any(
                        re.search(
                            r"from\s*['\"]vitest['\"]",
                            source,
                        )
                        for source in sources
                    )
                )
                needs_globals = uses_vitest and any(
                    self._uses_unimported_vitest_globals(source)
                    for source in sources
                )
                globals_enabled = self._vitest_globals_enabled(
                    self.workspace.root,
                    script,
                ) or "--globals" in extra
                if needs_globals and not globals_enabled:
                    return {
                        "ready": False,
                        "failure_kind": "vitest_globals_required",
                        "message": (
                            "Mevcut Vitest dosyaları describe/test/expect "
                            "global API'lerini kullanıyor. Doğrulama --globals "
                            "ile çalıştırılmalı."
                        ),
                        "remediation": {
                            "tool": "safe_terminal",
                            "arguments": {
                                "preset": "npm_test",
                                "extra_args": [*extra, "--globals"],
                            },
                            "requires_explicit_approval": False,
                        },
                        "runtime_revision": TERMINAL_RUNTIME_REVISION,
                    }

        return {
            "ready": True,
            "logical_command": logical,
            "runtime_revision": TERMINAL_RUNTIME_REVISION,
        }

    @staticmethod
    def _missing_result(
        *,
        preset: str,
        missing: str,
        logical: list[str],
        cwd: Path,
    ) -> dict[str, Any]:
        remediation: dict[str, Any] | None = None
        if missing == "npm":
            remediation = {
                "tool": "safe_terminal",
                "arguments": {"preset": "install_node_lts", "extra_args": []},
                "requires_explicit_approval": True,
            }

        return {
            "preset": preset,
            "command": logical,
            "logical_command": logical,
            "cwd": str(cwd),
            "exit_code": 127,
            "timed_out": False,
            "stdout": "",
            "stderr": f"Komut bulunamadı: {missing}",
            "truncated": False,
            "success": False,
            "failure_kind": "missing_command",
            "missing_command": missing,
            "remediation": remediation,
            "runtime_revision": TERMINAL_RUNTIME_REVISION,
        }

    def _command(self, arguments: dict[str, Any]) -> list[str]:
        _, _, logical = self._resolved_command(arguments)
        return logical

    async def preview(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command, missing, logical = self._resolved_command(arguments)
        return {
            "cwd": str(self.workspace.root),
            "command": command or logical,
            "logical_command": logical,
            "available": command is not None,
            "missing_command": missing,
            "timeout_seconds": self._timeout_for_preset(str(arguments.get("preset", ""))),
            "runtime_revision": TERMINAL_RUNTIME_REVISION,
        }

    async def execute(self, arguments: dict[str, Any]) -> Any:
        raise ToolError("safe_terminal yalnızca onaylı akışta çalışabilir.")

    def _run_sync(
        self,
        command: list[str],
        *,
        preset: str,
        logical: list[str],
    ) -> dict[str, Any]:
        env, path_entries = self._execution_environment(command)
        timeout = self._timeout_for_preset(preset)
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.workspace.root),
                capture_output=True,
                timeout=timeout,
                check=False,
                shell=False,
                env=env,
            )
            stdout_bytes = completed.stdout or b""
            stderr_bytes = completed.stderr or b""
            exit_code: int | None = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout_bytes = exc.stdout or b""
            stderr_bytes = exc.stderr or b""
            exit_code = None
            timed_out = True
        except FileNotFoundError:
            return self._missing_result(
                preset=preset,
                missing=logical[0],
                logical=logical,
                cwd=self.workspace.root,
            )
        except OSError as exc:
            detail = str(exc).strip() or type(exc).__name__
            return {
                "preset": preset,
                "command": command,
                "logical_command": logical,
                "cwd": str(self.workspace.root),
                "exit_code": 126,
                "timed_out": False,
                "stdout": "",
                "stderr": f"Komut işletim sistemi tarafından başlatılamadı: {detail}",
                "truncated": False,
                "success": False,
                "failure_kind": "command_launch_failed",
                "runtime_revision": TERMINAL_RUNTIME_REVISION,
            }

        if isinstance(stdout_bytes, str):
            stdout_text = stdout_bytes
        else:
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        if isinstance(stderr_bytes, str):
            stderr_text = stderr_bytes
        else:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        truncated = (
            len(stdout_text) > self.max_output_chars
            or len(stderr_text) > self.max_output_chars
        )

        return {
            "preset": preset,
            "command": command,
            "logical_command": logical,
            "cwd": str(self.workspace.root),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout": stdout_text[: self.max_output_chars],
            "stderr": stderr_text[: self.max_output_chars],
            "truncated": truncated,
            "success": exit_code == 0 and not timed_out,
            "runtime_revision": TERMINAL_RUNTIME_REVISION,
            "environment_path_entries": path_entries[:20],
            "timeout_seconds": timeout,
        }

    async def execute_approved(self, arguments: dict[str, Any]) -> Any:
        preset = str(arguments.get("preset", "")).strip()
        command, missing, logical = self._resolved_command(arguments)
        if command is None and missing is not None:
            return self._missing_result(
                preset=preset,
                missing=missing,
                logical=logical,
                cwd=self.workspace.root,
            )

        assert command is not None
        result = await asyncio.to_thread(
            self._run_sync,
            command,
            preset=preset,
            logical=logical,
        )

        if preset == "install_node_lts" and result.get("success") is True:
            result["npm_available_after_install"] = self._resolve_npm_base() is not None
        return result
