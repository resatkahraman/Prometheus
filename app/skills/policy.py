from __future__ import annotations

from fnmatch import fnmatchcase
from pathlib import PurePosixPath
from typing import Any
from app.agents.access import normalize, matches
from app.tools.base import ToolError
from app.tools.terminal import SAFE_TERMINAL_PRESETS, NETWORK_INTENT_TERMINAL_PRESETS
from .models import SkillManifest

TOOL_CAPABILITY_KIND = {
    "calculator":"compute","current_datetime":"compute","text_stats":"compute","symbolic_math":"compute",
    "project_summary":"filesystem.read","workspace_list":"filesystem.read","workspace_read":"filesystem.read","workspace_search":"filesystem.read","git_status":"filesystem.read","git_diff":"filesystem.read",
    "workspace_write":"filesystem.write","safe_terminal":"shell.execute",
}

class SkillCapabilityDeniedError(ToolError):
    pass

class SkillCapabilityPolicy:
    def authorize(
        self,
        *,
        manifest: SkillManifest,
        tool_name: str,
        arguments: dict[str, Any],
        invocation_write_paths: list[str] | tuple[str, ...] = (),
    ) -> None:
        if tool_name not in manifest.capabilities.tools: raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.")
        kind=TOOL_CAPABILITY_KIND.get(tool_name)
        if kind is None: raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.")
        if kind == "compute": return
        if kind.startswith("filesystem"):
            if kind.endswith("write") and ("path" not in arguments or not isinstance(arguments.get("path"), str) or not arguments.get("path", "").strip()):
                raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.")
            path=normalize(arguments.get("path", "."))
            patterns=manifest.capabilities.filesystem.write if kind.endswith("write") else manifest.capabilities.filesystem.read
            if kind.endswith("write") and invocation_write_paths:
                scoped: list[str] = []
                for raw_scope in invocation_write_paths:
                    if not isinstance(raw_scope, str) or not raw_scope.strip() or "\\" in raw_scope:
                        raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.")
                    try:
                        scoped.append(normalize(raw_scope))
                    except ToolError as exc:
                        raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.") from exc
                patterns = [*patterns, *scoped]
            if not patterns or not matches(path,patterns): raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.")
            return
        if kind == "shell.execute":
            preset=arguments.get("preset")
            if not isinstance(preset,str) or preset not in SAFE_TERMINAL_PRESETS or preset not in manifest.capabilities.shell.presets: raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.")
            if preset in NETWORK_INTENT_TERMINAL_PRESETS and (manifest.capabilities.network.mode != "approval_required" or "network" not in manifest.approval.required_for): raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.")
            return
        raise SkillCapabilityDeniedError("Skill capability policy denied the requested operation.")
