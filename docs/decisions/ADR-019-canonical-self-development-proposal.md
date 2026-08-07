# ADR-019 - Canonical Self-Development Proposal

Status: Accepted / Completed

Phase 3 begins with an immutable proposal identity rather than autonomous mutation. A proposal records a possible improvement and evidence provenance, but it does not prove correctness, evidence authenticity, human approval, execution authority or promotion authority. Its fixed safety flags are proposal-only, no automatic execution, no automatic promotion and no main-branch mutation.

The proposal kinds mirror the existing Forge vocabulary without modifying `CandidateKind` or the legacy Forge candidate payload. Existing Forge source-patch shadow/promotion behavior remains unchanged: source patches are lab-only and cannot be promoted automatically. A source-patch proposal contains only authorized existing source/test target paths and requires a complete `RepositoryMap` plus authoritative `ScopeLock`; it contains no exact edits, source, replacement, diff or executable patch.

Evidence references are structurally validated, canonically ordered and bound into the digest, but TASK-059 does not authenticate that external records exist. No timestamp is included, so equivalent requests are deterministic. The physical project root is held privately and never serialized.

Future flow: proposal -> trusted evidence resolution -> candidate materialization -> isolated evaluation -> supervised approval -> exact safe patch planning -> approval binding -> controlled execution/promotion. ApprovalManager, ImprovementStore, ImprovementService, Forge, benchmark, workspace patching, SafePatchExecutor, UI and Pandora remain unchanged.

Existing Forge is not replaced, and CandidateCreateRequest payload is not canonical proposal identity. Proposal kinds mirror current Forge kinds without changing CandidateKind. Every proposal requires evidence references; those references are bound but not independently authenticated in TASK-059. Source-patch proposals bind target scope, not exact edits, and require RepositoryMap and ScopeLock. Version-one targets are existing source/test files only; config/docs/other self-modification is deferred. Proposal identity excludes timestamps for deterministic semantic identity. Fixed safety flags prohibit execution, promotion and main mutation. Existing Forge source shadow behavior and its lab-only source-patch promotion restriction remain unchanged.

Validation:
- Targeted Self-Development Proposal suite: 5 passed.
- Focused self-development regression: 52 passed.
- Final full suite: 907 passed with 1 existing Starlette/httpx TestClient deprecation warning.
