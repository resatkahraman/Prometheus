# ADR-040: Desktop Packaging, Polish and Release

## Status

Accepted.

## Decision

Prometheus Desktop `0.1.0` is packaged as a Windows x86_64 NSIS release candidate using the approved Prometheus icon set. The package is intentionally unsigned and has no configured updater; neither a signing certificate nor an updater key or endpoint is fabricated.

The installer contains no bundled Ollama models and performs no automatic model download. Prometheus Desktop remains a bounded shell over the canonical workspace-managed Python Core runtime. It does not search for arbitrary Python interpreters, and its release diagnostics make the requirement, signing state and updater state explicit.

## Consequences

The generated release artifact is `Prometheus_0.1.0_x64-setup.exe`. It is suitable for automated release-candidate verification, while installer execution and end-to-end acceptance remain a separate supervised manual stage. Existing Core runtime, model-routing and native-OS authority boundaries remain unchanged.
