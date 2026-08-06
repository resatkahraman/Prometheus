from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any
from app.agents.registry import AgentRegistry
from app.core.config import Settings
from app.tools.registry import ToolRegistry
from app.tools.terminal import SAFE_TERMINAL_PRESETS, NETWORK_INTENT_TERMINAL_PRESETS
from .models import SkillCatalogResponse, SkillManifest, SkillManifestDocument, SkillManifestView
from .policy import SkillCapabilityPolicy, TOOL_CAPABILITY_KIND

SKILL_MANIFEST_SCHEMA_VERSION=1
SKILL_MANIFEST_PATH=Path(__file__).resolve().parents[2]/"config"/"skill_manifests.json"

class SkillManifestError(RuntimeError): pass
class SkillManifestValidationError(SkillManifestError): pass
class SkillManifestIntegrityError(SkillManifestError): pass
class SkillManifestNotFoundError(SkillManifestError): pass

def _digest(value: object) -> str:
    payload=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode("utf-8")
    return "sha256:"+hashlib.sha256(payload).hexdigest()

class SkillManifestRegistry:
    def __init__(self, *, manifests: list[SkillManifest], agents: AgentRegistry, tools: ToolRegistry, policy: SkillCapabilityPolicy | None = None) -> None:
        self.agents=agents; self.tools=tools; self.policy=policy or SkillCapabilityPolicy(); self._items={m.id:m for m in manifests}
        if len(self._items)!=len(manifests): raise SkillManifestIntegrityError("Skill manifest catalog is invalid.")
        if set(self._items)!=set(agents.ids()): raise SkillManifestIntegrityError("Skill manifest catalog is invalid.")
        available=set(tools.names())
        for m in manifests:
            try: profile=agents.get(m.id)
            except Exception as exc: raise SkillManifestIntegrityError("Skill manifest catalog is invalid.") from exc
            if m.entrypoint!=f"agent:{profile.id}" or m.name!=profile.name or m.capabilities.tools!=profile.allowed_tools or m.capabilities.filesystem.read!=profile.read_paths or m.capabilities.filesystem.write!=profile.write_paths or m.limits.max_steps!=profile.max_steps or m.limits.max_model_calls!=profile.max_model_calls: raise SkillManifestIntegrityError("Skill manifest catalog is invalid.")
            if not set(m.capabilities.tools)<=available or any(t not in TOOL_CAPABILITY_KIND for t in m.capabilities.tools): raise SkillManifestIntegrityError("Skill manifest catalog is invalid.")
            if not set(m.capabilities.shell.presets) <= set(SAFE_TERMINAL_PRESETS): raise SkillManifestIntegrityError("Skill manifest catalog is invalid.")
            if profile.read_only and set(m.capabilities.shell.presets) & set(NETWORK_INTENT_TERMINAL_PRESETS): raise SkillManifestIntegrityError("Skill manifest catalog is invalid.")
            if profile.read_only and "workspace_write" in m.capabilities.tools: raise SkillManifestIntegrityError("Skill manifest catalog is invalid.")
            for tool_name in ("workspace_write", "safe_terminal"):
                if tool_name in m.capabilities.tools and not tools.get(tool_name).requires_approval: raise SkillManifestIntegrityError("Skill manifest catalog is invalid.")
        self._views={m.id:SkillManifestView(manifest=m,manifest_digest=_digest(m.model_dump(mode="json"))) for m in manifests}
    def ids(self)->list[str]: return self.agents.ids()
    def all(self)->list[SkillManifestView]: return [self._views[i] for i in self.ids()]
    def get(self,skill_id:str)->SkillManifestView:
        if skill_id not in self._views: raise SkillManifestNotFoundError("Skill manifest not found.")
        return self._views[skill_id]
    def manifest(self,skill_id:str)->SkillManifest: return self.get(skill_id).manifest
    def authorize(self,*,skill_id:str,tool_name:str,arguments:dict[str,Any],invocation_write_paths:list[str] | tuple[str,...]=())->None:
        self.policy.authorize(manifest=self.manifest(skill_id),tool_name=tool_name,arguments=arguments,invocation_write_paths=invocation_write_paths)
    def catalog(self)->SkillCatalogResponse:
        items=self.all(); return SkillCatalogResponse(catalog_digest=_digest([i.manifest.model_dump(mode="json") for i in items]),items=items)

def build_default_skill_registry(*, settings: Settings, agents: AgentRegistry, tools: ToolRegistry, manifest_path: Path | None = None) -> SkillManifestRegistry:
    path=manifest_path or SKILL_MANIFEST_PATH
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>settings.skill_manifest_max_file_bytes: raise SkillManifestIntegrityError("Skill manifest catalog is unavailable.")
        document=SkillManifestDocument.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if len(document.skills)>settings.skill_manifest_max_entries: raise SkillManifestIntegrityError("Skill manifest catalog is unavailable.")
        return SkillManifestRegistry(manifests=document.skills,agents=agents,tools=tools)
    except SkillManifestError: raise
    except Exception as exc: raise SkillManifestIntegrityError("Skill manifest catalog is unavailable.") from exc
