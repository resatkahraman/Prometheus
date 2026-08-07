# TASK-051 — Context Bounds

Status: Completed

Baseline: `9b6b324fcb9b6655d009cc7233545a855c7c6313`
Branch: `task-051-context-bounds`

## Scope

TASK-051 adds a pure deterministic context-bound utility and applies hard character ceilings to Agent model input, Supervisor planner prompts and focused worker context. Required evidence is prioritized over supplementary memory, separators and wrapper text count toward limits, and no model-based compression is used.

Agent and Supervisor context remain bound to the TASK-050 Project Workspace snapshots. Existing ContextCompiler modes and fallback semantics are preserved. No new persistence, provider call, Pandora/UI change or dependency is introduced.

## Implementation summary

- deterministic `ContextBounds` utility;
- exact hard character ceilings after wrapper/assembly accounting;
- deterministic head/tail clipping;
- required-first priority assembly;
- Agent total model-input hard bound;
- Agent project-context sub-bound;
- Supervisor planner hard bound;
- Supervisor focused-context hard bound;
- required task evidence outranks supplementary Decision Memory;
- Project DNA remains authoritative high-priority project policy;
- compiler `off`, `shadow`, and `active` modes remain compatible;
- TASK-050 workspace snapshots remain authoritative;
- active project changes cannot retarget existing Agent sessions or Supervisor commands;
- no model-generated summarization;
- no provider/network call added;
- no prompt/source persistence added;
- no dependency added;
- no Pandora/UI changes.

## Narrow compatibility regression

Legacy partial `SupervisorService` construction via `__new__` lacked `self.settings`.
TASK-051 now uses a compatibility helper with a 24,000-character fallback,
matching the configured default, while normal production instances continue
using `settings.supervisor_planner_context_max_chars`.

## Test plan

Local deterministic tests cover clipping, digest determinism, head/tail retention, required-first assembly, separator accounting, planner/focused bounds and workspace snapshot isolation.

## Final validation

- Targeted: `7 passed in 0.26s`.
- Narrow compatibility regression: `2 passed, 1 warning in 1.26s`.
- Focused regression package: `132 passed, 1 warning in 8.26s`.
- Final full suite: `814 passed, 1 warning in 80.38s` (exit code `0`).
- Warning: pre-existing Starlette/httpx TestClient deprecation warning; not introduced by TASK-051.
