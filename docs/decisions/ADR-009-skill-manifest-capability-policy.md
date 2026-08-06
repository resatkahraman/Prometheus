# ADR-009 — Repository-Owned Skill Manifests and Default-Deny Capability Policy

Status: Accepted

## Context

Prometheus has several built-in agent profiles and an existing authorization/approval chain. Their capabilities must be explicit, reviewable, bounded, and deterministic without introducing a second authorization path.

## Decision

Every built-in executable agent is bound to one repository-owned manifest in `config/skill_manifests.json`. The startup registry validates that the catalog contains exactly the built-in agents and that each manifest matches the corresponding profile’s entrypoint, tools, filesystem scopes, and execution limits. Invalid, missing, oversized, symlinked, or unknown catalog content fails closed.

The skill policy is a default-deny gate before `AgentAccessController`. It classifies tools, validates filesystem scope and safe terminal presets, and requires explicit approvals for writes, shell execution, and network-intent presets. Existing access, approval, route, and provider gates remain independent and cannot be weakened by a manifest.

The catalog is exposed only through read-only metadata endpoints. Manifest data is immutable at runtime and includes bounded output, wall-time, step, and model-call limits. Network capability is currently intent classification and approval policy; process-level network isolation is a future control.

## Consequences

This creates a deterministic capability contract for every built-in skill and makes authorization failures observable without exposing secrets. Dynamic plugins, arbitrary entrypoints, marketplace/SDK installation, and general-purpose remote capability registration are deliberately excluded.
