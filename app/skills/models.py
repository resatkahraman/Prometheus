from __future__ import annotations

import fnmatch
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

SkillNetworkMode = Literal["none", "approval_required"]
SkillApprovalCapability = Literal["filesystem.write", "shell.execute", "network"]
_ID = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_ITEM = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")

def _list(values: list[str], *, pattern: re.Pattern[str] | None = None, path=False) -> list[str]:
    if not isinstance(values, list): raise ValueError("list required")
    result=[]
    for value in values:
        if not isinstance(value,str): raise ValueError("list items must be strings")
        value=value.strip()
        if not value or value in result: raise ValueError("empty or duplicate capability")
        if len(value)>300: raise ValueError("capability item too long")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("control character is not allowed")
        if path:
            if "\\" in value or value.startswith("/") or re.match(r"^[A-Za-z]:",value) or ".." in value.split("/"):
                raise ValueError("filesystem pattern is invalid")
        elif pattern and not pattern.fullmatch(value): raise ValueError("identifier is invalid")
        result.append(value)
    return result

class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

class SkillFilesystemCapabilities(_Frozen):
    read: list[str]
    write: list[str] = Field(default_factory=list)
    @model_validator(mode="after")
    def normalize(self):
        object.__setattr__(self,"read",_list(self.read,path=True)); object.__setattr__(self,"write",_list(self.write,path=True)); return self

class SkillShellCapabilities(_Frozen):
    presets: list[str] = Field(default_factory=list)
    @model_validator(mode="after")
    def normalize(self): object.__setattr__(self,"presets",_list(self.presets,pattern=_ITEM)); return self

class SkillNetworkCapabilities(_Frozen):
    mode: SkillNetworkMode = "none"

class SkillCapabilities(_Frozen):
    tools: list[str]
    filesystem: SkillFilesystemCapabilities
    shell: SkillShellCapabilities = Field(default_factory=SkillShellCapabilities)
    network: SkillNetworkCapabilities = Field(default_factory=SkillNetworkCapabilities)
    @model_validator(mode="after")
    def normalize(self): object.__setattr__(self,"tools",_list(self.tools,pattern=_ITEM)); return self

class SkillLimits(_Frozen):
    max_steps: int = Field(ge=1,le=40)
    max_model_calls: int = Field(ge=1,le=50)
    max_output_tokens: int = Field(ge=128,le=16_384)
    max_wall_time_seconds: float = Field(ge=1.0,le=3_600.0)
    max_output_bytes: int = Field(ge=1_024,le=10_000_000)

class SkillApprovalPolicy(_Frozen):
    required_for: list[SkillApprovalCapability] = Field(default_factory=list)
    @model_validator(mode="after")
    def unique(self):
        if len(self.required_for)!=len(set(self.required_for)): raise ValueError("duplicate approval capability")
        return self

class SkillManifest(_Frozen):
    schema_version: Literal[1] = 1
    id: str
    name: str
    version: str
    description: str
    entrypoint: str
    capabilities: SkillCapabilities
    limits: SkillLimits
    approval: SkillApprovalPolicy
    @model_validator(mode="after")
    def validate_manifest(self):
        if not _ID.fullmatch(self.id): raise ValueError("skill id invalid")
        if not self.name.strip() or len(self.name)>160 or not self.description.strip() or len(self.description)>2000: raise ValueError("skill text invalid")
        if not _VERSION.fullmatch(self.version) or self.entrypoint != f"agent:{self.id}": raise ValueError("skill identity invalid")
        tools=set(self.capabilities.tools); approvals=set(self.approval.required_for)
        if "workspace_write" in tools and (not self.capabilities.filesystem.write or "filesystem.write" not in approvals): raise ValueError("write capability requires scope and approval")
        if "workspace_write" not in tools and self.capabilities.filesystem.write: raise ValueError("read-only skill cannot write")
        if "safe_terminal" in tools and (not self.capabilities.shell.presets or "shell.execute" not in approvals): raise ValueError("shell capability requires approval")
        if "safe_terminal" not in tools and self.capabilities.shell.presets: raise ValueError("shell presets require safe_terminal")
        network_presets={"npm_install","npm_install_dev","install_node_lts","pip_install_dev"}
        if network_presets & set(self.capabilities.shell.presets):
            if self.capabilities.network.mode!="approval_required" or "network" not in approvals: raise ValueError("network intent requires approval")
        elif self.capabilities.network.mode=="approval_required" or "network" in approvals: raise ValueError("undeclared network approval")
        if any(cap not in {"filesystem.write","shell.execute","network"} for cap in approvals): raise ValueError("unknown approval capability")
        return self

class SkillManifestDocument(_Frozen):
    schema_version: Literal[1] = 1
    skills: list[SkillManifest]

class SkillManifestView(_Frozen):
    manifest: SkillManifest
    manifest_digest: str

class SkillCatalogResponse(_Frozen):
    schema_version: Literal[1] = 1
    catalog_digest: str
    items: list[SkillManifestView]
