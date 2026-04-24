# MobiFlow

MobiFlow is an intelligent mobile experiment execution platform for complex, non-deterministic app workflows.

This repository contains the three core parts of the system:

- `MobiFlow_Agent`
  Task planning, dynamic orchestration, governed execution, evidence-based verification, recovery, and task memory.
- `AI_Mobile_Executor_Platform`
  Platform control plane, execution governance, APIs, operational workflows, and web console.
- `AutoA11y_Executor`
  Android-side executor for real device interaction, accessibility-driven actions, shell fallback, runtime observation, and reporting.

## Architecture

MobiFlow is organized as a three-layer system:

1. Agent decision layer
   Responsible for goal understanding, task decomposition, dynamic step routing, verification, recovery, and memory-enhanced execution.
2. Platform control plane
   Responsible for state management, governance, approval, auditing, API orchestration, and operator-facing tools.
3. Android executor
   Responsible for real device actions, runtime observation, app state recovery, and artifact reporting.

## Repository Layout

```text
MobiFlow/
  AI_Mobile_Executor_Platform/   # control plane and platform services
  AutoA11y_Executor/             # Android executor
  MobiFlow_Agent/                # agent runtime and evaluation
```

## Notes

- Archived design drafts, migration notes, and intermediate working materials are intentionally excluded from this repository.
- Each subproject keeps its own local documentation and build configuration.

