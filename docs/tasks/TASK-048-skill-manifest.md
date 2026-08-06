# TASK-048 — Skill Manifest and Capability Policy

Status: Completed and validated.

Baseline before TASK-048: `0d823669be99c94fd89c9a7f8b5b38045b2029c7`.

## Purpose

TASK-048 gives each built-in agent a repository-owned, immutable skill manifest. The manifest binds the agent profile to its tools, filesystem scopes, shell presets, network intent, approval requirements, and bounded runtime/output limits.

## Implementation

- `config/skill_manifests.json` is the canonical catalog for all ten built-in skills.
- The registry validates the catalog at startup, rejects unknown or missing agents/tools, and fails closed on malformed, oversized, or symlinked files.
- Capability policy runs before the existing agent access guard; it cannot broaden existing authorization or approval requirements.
- Agent execution resolves a manifest before work begins and enforces manifest step, model-call, wall-time, token, and output-byte limits.
- Read-only skill catalog endpoints expose deterministic metadata with no-store responses.

## Security boundaries

Unknown tools, paths, shell presets, network-intent presets, and undeclared approvals are denied. Existing workspace, approval, provider, and route protections remain independent gates. Dynamic plugins, arbitrary entrypoints, and marketplace/SDK installation are out of scope.

<!-- TASK-048-VALIDATION-RESULTS -->
## Final validation

- Task-specific Skill Manifest tests: `42 passed`.
- Focused capability and Agent regression: `105 passed`.
- Post-repair regression package: `63 passed`.
- Final full suite: `792 passed, 1 warning`.
- Static validation: `py_compile`, JSON, registry build and AST checks passed.
- Whitespace validation: `git diff --check` passed.
- Warning: existing Starlette TestClient/httpx deprecation warning; no failures.
- No Pandora, UI or dependency changes.
