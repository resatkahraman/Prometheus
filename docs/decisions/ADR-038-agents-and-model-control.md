# ADR-038: Agents and Model Control

Status: Accepted and validated.

Prometheus routes model work through canonical capability metadata. The local generation default is `gemma4:e4b-it-qat`, new semantic indexes use `embeddinggemma:300m-qat-q4_0`, and structured-output/tool-routing recommendations use `ministral-3:3b`.

Persisted embeddings bind their model identity and dimensions. Vectors from a different model are never silently compared or automatically migrated; the index reports that an explicit rebuild is required. Provider availability checks are bounded and read-only. They never download a model or accept a Desktop-supplied provider URL.

Model output is untrusted input. Existing parsing, schema validation, approval, workspace policy and bounded execution authority remain canonical.
