from pydantic import BaseModel, Field, field_validator

from app.core.schemas import TaskType


class AgentProfile(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    name: str
    short_name: str
    description: str
    mission: list[str]
    preferred_routes: list[str]
    allowed_tools: list[str]
    read_paths: list[str] = Field(default_factory=lambda: ["**"])
    write_paths: list[str] = Field(default_factory=list)
    read_only: bool = False
    max_steps: int = Field(default=10, ge=1, le=40)
    max_model_calls: int = Field(default=12, ge=1, le=50)
    temperature: float = Field(default=0.1, ge=0, le=1)
    task_type_override: TaskType | None = None
    auto_context: bool = False
    output_contract: list[str] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)

    @field_validator(
        "mission",
        "preferred_routes",
        "allowed_tools",
        "read_paths",
        "write_paths",
        "output_contract",
        "instructions",
    )
    @classmethod
    def dedupe(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    def prompt_block(self) -> str:
        def bullets(items: list[str]) -> str:
            return "\n".join(f"- {item}" for item in items) or "- Yok"

        return f"""Agent kimliği: {self.id}
Agent adı: {self.name}
Rol: {self.description}

Misyon:
{bullets(self.mission)}

Rol kuralları:
{bullets(self.instructions)}

Yazma kapsamı:
{", ".join(self.write_paths) if self.write_paths else "Yazma yetkisi yok."}

ZORUNLU çıktı sözleşmesi:
{bullets(self.output_contract)}"""
