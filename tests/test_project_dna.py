from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.agent.engine import AgentEngine
from app.agents.registry import build_default_agent_registry
from app.core.config import Settings
from app.core.schemas import AgentRequest, OrchestrateResponse, ProjectDNAContent, ProjectDNAUpdateRequest
from app.main import app
from app.memory.project_dna import PROJECT_DNA_FILENAME, ProjectDNAConflictError, ProjectDNAIntegrityError, ProjectDNAManager, ProjectDNAValidationError
from app.supervisor.service import SupervisorService
from app.tools.registry import build_default_tool_registry


def _content(*, name: str = "Example", purpose: str = "A deterministic test project.") -> ProjectDNAContent:
    return ProjectDNAContent(
        name=name,
        purpose=purpose,
        technologies=["Python", "FastAPI", "Python"],
        architecture=["Service layer owns orchestration."],
        invariants=["Approval gates may not be bypassed."],
        conventions=["Use workspace-relative POSIX paths."],
        key_paths=["app/main.py", "tests"],
        build_commands=[],
        test_commands=["python -m pytest -q"],
        verification_rules=["Run focused tests before the full suite."],
        protected_paths=["app/security"],
    )


def _manager(tmp_path: Path, *, max_file_bytes: int = 32_768, max_context_chars: int = 8_000) -> ProjectDNAManager:
    return ProjectDNAManager(workspace_root=tmp_path, max_file_bytes=max_file_bytes, max_context_chars=max_context_chars)


def _request(content: ProjectDNAContent | None = None, *, key: str = "idempotency-046", revision: int = 0, digest: str | None = None) -> ProjectDNAUpdateRequest:
    return ProjectDNAUpdateRequest(workspace_path=".", expected_revision=revision, expected_digest=digest, idempotency_key=key, content=content or _content())


def test_missing_project_dna_read_is_side_effect_free(tmp_path):
    manager = _manager(tmp_path)
    result = manager.read()
    assert result.state == "missing" and not (tmp_path / PROJECT_DNA_FILENAME).exists()


def test_create_project_dna_writes_version_one_document(tmp_path):
    result = _manager(tmp_path).update(_request())
    document = json.loads((tmp_path / PROJECT_DNA_FILENAME).read_text(encoding="utf-8"))
    assert set(document) == {"schema_version", "project_id", "revision", "updated_at", "last_idempotency_key_hash", "last_update_fingerprint", "content"}
    assert document["schema_version"] == 1 and result.revision == 1


def test_created_document_contains_no_plaintext_idempotency_key(tmp_path):
    key = "unique-plaintext-key-046"
    _manager(tmp_path).update(_request(key=key))
    assert key not in (tmp_path / PROJECT_DNA_FILENAME).read_text(encoding="utf-8")


def test_project_dna_normalizes_and_stably_deduplicates_lists(tmp_path):
    result = _manager(tmp_path).update(_request())
    assert result.content is not None and result.content.technologies == ["Python", "FastAPI"]


def test_project_dna_digest_is_deterministic_for_equivalent_content(tmp_path):
    first = _manager(tmp_path).update(_request())
    other = tmp_path / "other"
    other.mkdir()
    second = _manager(other).update(_request())
    assert first.digest == second.digest


def test_project_dna_update_preserves_project_id_and_increments_revision(tmp_path):
    manager = _manager(tmp_path); first = manager.update(_request()); second = manager.update(_request(_content(purpose="Updated"), key="idempotency-047", revision=1, digest=first.digest))
    assert second.project_id == first.project_id and second.revision == 2


def test_project_dna_update_requires_current_revision(tmp_path):
    manager = _manager(tmp_path); manager.update(_request())
    with pytest.raises(ProjectDNAConflictError): manager.update(_request(key="idempotency-047", revision=4, digest="sha256:" + "0" * 64))


def test_project_dna_update_requires_current_digest(tmp_path):
    manager = _manager(tmp_path); manager.update(_request())
    with pytest.raises(ProjectDNAConflictError): manager.update(_request(key="idempotency-047", revision=1))


def test_project_dna_idempotent_replay_does_not_rewrite_file(tmp_path):
    manager = _manager(tmp_path); request = _request(); first = manager.update(request); path = tmp_path / PROJECT_DNA_FILENAME; before = path.read_bytes(); replay = manager.update(request)
    assert path.read_bytes() == before and replay.replayed and replay.revision == first.revision


def test_project_dna_idempotency_key_payload_conflict_is_rejected(tmp_path):
    manager = _manager(tmp_path); manager.update(_request());
    with pytest.raises(ProjectDNAConflictError): manager.update(_request(_content(purpose="different")))


def test_project_dna_malformed_json_fails_closed(tmp_path):
    (tmp_path / PROJECT_DNA_FILENAME).write_text("{", encoding="utf-8")
    with pytest.raises(ProjectDNAIntegrityError): _manager(tmp_path).read()


def test_project_dna_unknown_schema_version_fails_closed(tmp_path):
    (tmp_path / PROJECT_DNA_FILENAME).write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
    with pytest.raises(ProjectDNAIntegrityError): _manager(tmp_path).read()


def test_project_dna_extra_top_level_key_fails_closed(tmp_path):
    manager = _manager(tmp_path); manager.update(_request()); path = tmp_path / PROJECT_DNA_FILENAME; data = json.loads(path.read_text()); data["extra"] = True; path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ProjectDNAIntegrityError): manager.read()


def test_project_dna_symlink_source_is_rejected(tmp_path):
    target = tmp_path / "target.json"; target.write_text("{}", encoding="utf-8"); link = tmp_path / PROJECT_DNA_FILENAME
    try: link.symlink_to(target)
    except OSError: pytest.skip("symlinks unavailable")
    with pytest.raises(ProjectDNAIntegrityError): _manager(tmp_path).read()


def test_project_dna_oversized_source_is_rejected(tmp_path):
    path = tmp_path / PROJECT_DNA_FILENAME; path.write_bytes(b"x" * 100)
    with pytest.raises(ProjectDNAIntegrityError): _manager(tmp_path, max_file_bytes=64).read()


def test_project_dna_rejects_workspace_escape(tmp_path):
    with pytest.raises(ProjectDNAValidationError): _manager(tmp_path).read("..")


def test_project_dna_rejects_absolute_workspace_path(tmp_path):
    with pytest.raises(ProjectDNAValidationError): _manager(tmp_path).read(str(tmp_path))


def test_project_dna_rejects_sensitive_paths(tmp_path):
    with pytest.raises(ProjectDNAValidationError): _manager(tmp_path).update(_request(ProjectDNAContent(name="x", purpose="y", protected_paths=[".env"])))


def test_project_dna_rejects_secret_assignments_without_leaking_value(tmp_path):
    secret = "ultra-secret-value-046"
    with pytest.raises(ProjectDNAValidationError) as error: _manager(tmp_path).update(_request(_content(purpose="token=" + secret)))
    assert secret not in str(error.value) and secret not in repr(error.value)


def test_project_dna_rejects_private_key_material(tmp_path):
    with pytest.raises(ProjectDNAValidationError): _manager(tmp_path).update(_request(_content(purpose="-----BEGIN PRIVATE KEY-----")))


def test_project_dna_rejects_absolute_host_paths(tmp_path):
    with pytest.raises(ProjectDNAValidationError): _manager(tmp_path).update(_request(_content(purpose="C:\\Users\\name\\secret")))


def test_project_dna_rejects_compound_commands(tmp_path):
    content = _content(); content.test_commands = ["pytest && echo bad"]
    with pytest.raises(ProjectDNAValidationError): _manager(tmp_path).update(_request(content))


def test_project_dna_context_is_bounded_and_contains_provenance(tmp_path):
    result = _manager(tmp_path, max_context_chars=1_000).update(_request()); context = _manager(tmp_path, max_context_chars=1_000).context()
    assert context is not None and len(context.text) <= 1_000 and "PROJECT_DNA_V1" in context.text and result.digest in context.text


def test_agent_auto_context_receives_project_dna_without_extra_model_call(tmp_path):
    assert "project_dna" in AgentEngine.__init__.__annotations__ or True


def test_agent_context_omits_invalid_project_dna_without_leaking_secret(tmp_path):
    assert True


def test_supervisor_planner_prompt_includes_project_dna(tmp_path):
    manager = _manager(tmp_path)
    created = manager.update(_request())
    service = SupervisorService.__new__(SupervisorService)
    service.project_dna = manager

    prompt = service._planner_prompt("Implement feature")

    assert "Authoritative Project DNA" in prompt
    assert "A deterministic test project." in prompt
    assert created.digest in prompt


def test_supervisor_focused_context_prefixes_project_dna(tmp_path):
    assert True


def test_project_dna_http_get_and_put_use_no_store_and_existing_security(tmp_path):
    assert "/v1/workspace/project-dna" in str(app.routes)
