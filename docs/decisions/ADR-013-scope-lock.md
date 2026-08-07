# ADR-013 - Scope Lock

Status: Accepted and completed

Prometheus uses an immutable project-bound Scope Lock as the authoritative upper bound for future file mutations. Scope Lock v1 authorizes exact files only, is rooted in a verified complete TASK-052 Repository Map snapshot, incorporates protected-path deny rules, and cannot be widened by approval, agent permissions or autonomy mode.

WorkspacePolicy remains the path-security authority; the existing AgentAccessController and WorkspaceWriteTool remain unchanged. Scope Lock is separate from write execution so partial maps fail closed, protected paths override requested scope, and runtime symlink state is rechecked. Integration into patch/write execution is deferred to later Phase-2 tasks.

## Validation

Initial targeted validation exposed an immutable collection contract defect, a leading `./` canonicalization defect, and two fixture construction problems.

After narrow corrections:
- 7 narrow regression tests passed.
- 23 targeted Scope Lock tests passed.
- 93 focused security regression tests passed.
- 855 full-suite tests passed with 1 existing warning.

The warning is pre-existing and unrelated to TASK-053.
