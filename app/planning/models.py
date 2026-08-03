from typing import Literal

from pydantic import BaseModel, Field


TaskPriority = Literal["zorunlu", "önerilen", "opsiyonel"]
EvidenceType = Literal[
    "file",
    "user_request",
    "verified_gap",
    "assumption",
]
ApprovalRequirement = Literal["gerekmez", "gerekli"]
ParallelFlag = Literal["evet", "hayır"]


class PlanEvidence(BaseModel):
    type: EvidenceType
    value: str = Field(min_length=1)


class PlanTask(BaseModel):
    id: str = Field(pattern=r"^TASK-\d{3}$")
    title: str = Field(min_length=3)
    priority: TaskPriority
    assigned_agent: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    evidence: list[PlanEvidence] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)
    dependency_reason: str = Field(min_length=2)
    parallelizable: ParallelFlag
    verification: str = Field(min_length=3)
    user_approval: ApprovalRequirement
    exact_files: list[str] = Field(default_factory=list)


class PlanningDocument(BaseModel):
    verified_facts: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    tasks: list[PlanTask] = Field(min_length=1)
    critical_decisions: list[str] = Field(default_factory=list)
