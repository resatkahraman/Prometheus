# TASK-059 - Canonical Self-Development Proposal

Status: Implemented; validation pending
Branch: task-059-supervised-self-development
Baseline: cfa6c95acc052704a05a476eeadbbd727f56b236

## Scope

TASK-059 is the first Phase-3 primitive. It defines an immutable, deterministic, evidence-referenced proposal describing a possible self-development improvement. It is read-only and does not persist, evaluate, approve, execute, promote or mutate anything.

## Contract

The proposal supports `strategy`, `prompt_delta`, `router_policy` and `source_patch`. Every proposal requires canonical evidence references. Logical kinds have no filesystem scope. `source_patch` requires a complete RepositoryMap and ScopeLock, existing map membership, authorized source/test roles and canonical target ordering. It stores no source text, replacement, patch or exact edit.

The digest binds project identity, proposal text, evidence, targets, map/scope identity where applicable and fixed safety flags. Evidence structure is validated but external evidence authenticity is deferred. The physical project root remains private, and runtime construction is snapshot-bound.

Existing ImprovementStore, ImprovementService, Forge, CandidateCreateRequest, benchmark, promotion/rollback, workspace patch stack, approval stack and Pandora/UI remain unchanged. Future work may materialize candidates, resolve trusted evidence and connect supervised safe-patch planning; automatic evolution and main mutation remain out of scope.

## Validation

The implementation is prepared for the targeted proposal, scope and determinism tests. Pytest is not run by Codex under the task execution restrictions.

## Finalized architecture

Revision: `self-development-proposal-v1`.

TASK-059 is proposal-only and read-only. A canonical proposal describes possible improvement intent; it does not authorize execution or promotion, prove correctness or human approval, or mutate `main`. Existing PrometheusForge, CandidateCreateRequest, candidate persistence, evaluation, promotion/rollback and the source-patch lab-only restriction remain unchanged.

Every proposal requires at least one structurally validated, canonically ordered evidence reference of kind `experience_episode`, `benchmark_run` or `execution_receipt`. References are cryptographically bound but are not independently authenticated or resolved by TASK-059; duplicate references fail closed.

Canonical identity binds workspace/project identity, kind, title, rationale, expected outcome, evidence and counts, target paths and counts, applicable RepositoryMap/ScopeLock digests and fixed safety flags. Timestamps are excluded, so semantically equivalent requests have stable digests. Logical kinds allow no target paths or map/scope; their digests are `None`.

For `source_patch`, RepositoryMap and ScopeLock are mandatory and complete; targets must already be mapped existing files with `source` or `test` roles. `ScopeLock.assert_write()` remains authoritative, protected paths fail closed, targets are sorted and unique, and map/scope digests are bound. The proposal stores no source, replacement, diff, patch body, search/replace payload, SafePatchPlan, SafePatchApprovalBinding or executable command: it separates “I propose changing these files” from exact executable edits.

The physical project root is private and not serialized. `from_runtime` is snapshot-bound and does not reread active project selection. No repository, `.adam`, SQLite, Forge, benchmark, SafePatch, Git, subprocess, network, model, CWD or dependency side effect occurs.

## Final validation

- Targeted: `5 passed`.
- Focused self-development regression: `52 passed`.
- Final full suite: `907 passed, 1 existing warning`.
- Warning: existing Starlette/httpx TestClient deprecation warning; not introduced by TASK-059.
