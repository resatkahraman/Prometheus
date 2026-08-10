# ADR-021 - Canonical Self-Development Candidate Materialization

Status: Accepted

Canonical self-development candidates are immutable deterministic project-bound artifacts derived only from a validated canonical proposal and its matching trusted evidence resolution.

The materialization chain is:

```text
proposal digest
    +
trusted evidence resolution digest
    ->
candidate identity/digest
```

Candidate materialization has no execution, mutation, evaluation, promotion, approval, model, tool, network or Git side effects. Safety flags remain fixed to require human approval and prohibit execution, source mutation and main-branch mutation.

The next stage is isolated candidate evaluation.
