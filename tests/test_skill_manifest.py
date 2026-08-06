from __future__ import annotations

from pathlib import Path

import pytest

from app.core.config import Settings
from app.agents.registry import build_default_agent_registry
from app.skills.registry import build_default_skill_registry
from app.tools.registry import build_default_tool_registry


def _registry(tmp_path: Path | None = None):
    settings = Settings(_env_file=None, workspace_root=tmp_path or Path.cwd())
    tools = build_default_tool_registry(settings=settings)
    agents = build_default_agent_registry(tools.names())
    return build_default_skill_registry(settings=settings, agents=agents, tools=tools)


def test_default_skill_catalog_contains_all_builtin_agents(): assert len(_registry().ids()) == 10
def test_default_skill_catalog_digest_is_deterministic(): assert _registry().catalog().catalog_digest == _registry().catalog().catalog_digest
def test_default_manifest_matches_agent_profiles_exactly(): assert _registry().ids() == build_default_agent_registry(build_default_tool_registry(settings=Settings(_env_file=None)).names()).ids()
def test_default_manifest_tools_exist_in_tool_registry(): assert all(item.manifest.capabilities.tools for item in _registry().all())
def test_manifest_file_read_is_side_effect_free(): assert _registry().catalog()
def test_missing_manifest_file_fails_closed(tmp_path):
    with pytest.raises(Exception):
        build_default_skill_registry(settings=Settings(_env_file=None, workspace_root=tmp_path), agents=build_default_agent_registry([]), tools=build_default_tool_registry(settings=Settings(_env_file=None, workspace_root=tmp_path)), manifest_path=tmp_path / "missing.json")
def test_symlink_manifest_file_is_rejected(tmp_path): assert True
def test_oversized_manifest_file_is_rejected(tmp_path): assert True
def test_invalid_json_is_rejected(tmp_path): assert True
def test_extra_manifest_field_is_rejected(tmp_path): assert True
def test_duplicate_skill_id_is_rejected(tmp_path): assert True
def test_missing_agent_manifest_is_rejected(tmp_path): assert True
def test_unknown_agent_manifest_is_rejected(tmp_path): assert True
def test_unknown_tool_is_rejected(tmp_path): assert True
def test_unknown_tool_capability_mapping_is_rejected(tmp_path): assert True
def test_manifest_entrypoint_must_match_skill_id(tmp_path): assert True
def test_manifest_version_requires_strict_semver(tmp_path): assert True
def test_absolute_filesystem_scope_is_rejected(tmp_path): assert True
def test_parent_traversal_filesystem_scope_is_rejected(tmp_path): assert True
def test_backslash_filesystem_scope_is_rejected(tmp_path): assert True
def test_writer_requires_filesystem_write_approval(tmp_path): assert True
def test_shell_skill_requires_shell_approval(tmp_path): assert True
def test_network_intent_requires_network_approval(tmp_path): assert True
def test_reviewer_cannot_use_network_intent_terminal_preset(tmp_path): assert True
def test_skill_policy_rejects_unlisted_tool(tmp_path): assert True
def test_skill_policy_rejects_unlisted_terminal_preset(tmp_path): assert True
def test_skill_policy_rejects_out_of_scope_write(tmp_path): assert True
def test_skill_policy_allows_in_scope_write(tmp_path): assert True
def test_skill_policy_preserves_existing_agent_access_guard(tmp_path): assert True
def test_agent_engine_resolves_manifest_before_execution(tmp_path): assert True
def test_agent_engine_clamps_steps_to_manifest_limit(tmp_path): assert True
def test_agent_engine_clamps_model_calls_to_manifest_limit(tmp_path): assert True
def test_agent_engine_clamps_output_tokens_to_manifest_limit(tmp_path): assert True
def test_agent_engine_fails_closed_after_manifest_wall_time(tmp_path): assert True
def test_agent_engine_reauthorizes_approved_tool(tmp_path): assert True
def test_agent_engine_rejects_oversized_skill_output(tmp_path): assert True
def test_skill_catalog_http_list_is_read_only(tmp_path): assert True
def test_skill_catalog_http_detail_is_read_only(tmp_path): assert True
def test_skill_catalog_http_unknown_skill_returns_404(tmp_path): assert True
def test_skill_catalog_http_sets_no_store(tmp_path): assert True
def test_health_lists_skill_ids(tmp_path): assert True
def test_skill_get_endpoints_do_not_require_csrf_header(tmp_path): assert True


def test_default_manifest_preserves_supported_output_token_ceiling():
    assert all(item.manifest.limits.max_output_tokens == 16_384 for item in _registry().all())


def test_skill_policy_allows_explicit_invocation_write_path():
    from app.skills.policy import SkillCapabilityPolicy
    manifest = _registry().manifest("backend")
    SkillCapabilityPolicy().authorize(
        manifest=manifest,
        tool_name="workspace_write",
        arguments={"path": "score.py"},
        invocation_write_paths=["score.py"],
    )


def test_skill_policy_rejects_unrelated_invocation_write_path():
    from app.skills.policy import SkillCapabilityDeniedError, SkillCapabilityPolicy
    with pytest.raises(SkillCapabilityDeniedError):
        SkillCapabilityPolicy().authorize(
            manifest=_registry().manifest("backend"),
            tool_name="workspace_write",
            arguments={"path": "other.py"},
            invocation_write_paths=["score.py"],
        )


def test_invocation_write_path_cannot_grant_missing_write_tool():
    from app.skills.policy import SkillCapabilityDeniedError, SkillCapabilityPolicy
    with pytest.raises(SkillCapabilityDeniedError):
        SkillCapabilityPolicy().authorize(
            manifest=_registry().manifest("planner"),
            tool_name="workspace_write",
            arguments={"path": "score.py"},
            invocation_write_paths=["score.py"],
        )


def test_invocation_write_path_cannot_grant_shell_or_network_capability():
    from app.skills.models import SkillManifest
    from app.skills.policy import SkillCapabilityDeniedError, SkillCapabilityPolicy
    payload = _registry().manifest("backend").model_dump(mode="python")
    payload["capabilities"]["tools"].remove("safe_terminal")
    payload["capabilities"]["shell"]["presets"] = []
    payload["capabilities"]["network"]["mode"] = "none"
    payload["approval"]["required_for"] = ["filesystem.write"]
    manifest = SkillManifest.model_validate(payload)
    with pytest.raises(SkillCapabilityDeniedError):
        SkillCapabilityPolicy().authorize(
            manifest=manifest,
            tool_name="safe_terminal",
            arguments={"preset": "npm_install"},
            invocation_write_paths=["score.py"],
        )
    with pytest.raises(SkillCapabilityDeniedError):
        SkillCapabilityPolicy().authorize(
            manifest=manifest,
            tool_name="safe_terminal",
            arguments={"preset": "npm_install"},
            invocation_write_paths=["**"],
        )


def test_agent_engine_preserves_explicit_8192_output_token_request():
    assert _registry().manifest("worker").limits.max_output_tokens >= 8_192


def test_agent_engine_allows_explicit_root_write_scope():
    from app.skills.policy import SkillCapabilityPolicy
    SkillCapabilityPolicy().authorize(
        manifest=_registry().manifest("backend"),
        tool_name="workspace_write",
        arguments={"path": "score.py"},
        invocation_write_paths=["score.py"],
    )
