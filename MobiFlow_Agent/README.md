# MobiFlow Agent

MobiFlow Agent is the task-first decision and orchestration layer of MobiFlow. It targets mobile workflows that cannot be handled reliably by a fixed script: permission dialogs, slow loading pages, wrong-page transitions, approval-required actions, and recoverable UI drift.

## Current Status

- Main runtime: `TaskGraphRuntime`, backed by LangGraph.
- Compatibility name: `TaskOrchestratorService`, graph-backed.
- Current verified test baseline: `416 passed`.
- Scope: Agent runtime, simulation, memory, evaluation, and traceability. Real-device execution remains outside this subproject.

## Core Workflow

```text
goal
  -> plan
  -> observe
  -> decide_step
  -> execute proposal
  -> verify
  -> recover / replan if needed
  -> memory writeback
  -> trace export
```

`TaskSession` remains the authoritative business state. LangGraph state only carries orchestration control fields.

## Recent Agent Enhancements

- Model-driven `StepPolicyAgent` with bounded `StepDecision` output.
- `StepPolicyDecisionValidator` for tool allowlist, target alignment, decision consistency, and evidence readiness.
- Structured `VerificationPredicate` support for success checks.
- Structured `blocked_checks` and verifier diagnostics for permission dialogs, wrong pages, loading screens, and other negative states.
- Dynamic recovery scenarios, including slow-loading retry and fixed-script contrast.
- Task memory applicability, confidence scoring, feedback, and retrieval explanations.
- `ExecutionTraceExporter` with JSON, Markdown, redaction, and node-level timeline output.
- Scenario regression suite grouped by normal, recovery, approval, fixed-script contrast, and memory capabilities.

## Package Responsibilities

```text
mobiflow_agent/
  graph/        LangGraph runtime, nodes, routes, and graph support ops
  agents/       planner, observer, step policy, executor, verifier, recovery
  task/         TaskSession, TaskPlan, TaskStep, task status models
  runtime/      harness, checkpointing, context compression, trace export
  memory/       task memory records, retrieval, quality, governance, feedback
  evaluation/   simulation scenarios, quality gates, regression suite
  platform/     simulated mobile adapter and platform contracts
  model/        provider-agnostic generation and embedding runtime
  control/      dispatcher, policy, and compatibility imports
  common/       canonical contracts and id helpers
```

## Minimal Runtime Example

```python
from mobiflow_agent import EntityKind, TaskGraphRuntime, VerificationCheck, VerificationSpec

runtime = TaskGraphRuntime()

session = runtime.create_session(
    "[dynamic] Login to the demo app using bounded mobile UI actions.",
    target_kind=EntityKind.TASK,
    target_id="dynamic_login_success",
    verification_spec=VerificationSpec(
        verification_id="verification:demo-login",
        target_kind=EntityKind.TASK,
        target_id="dynamic_login_success",
        success_checks=[
            VerificationCheck(
                check_id="home-screen-visible",
                description="Home Screen is visible.",
                evidence_hint="Home Screen",
            )
        ],
    ),
)

session = runtime.run(session)
```

## Scenario Regression Suite

```python
from mobiflow_agent import ScenarioRegressionSuiteRunner

report = ScenarioRegressionSuiteRunner().run_default_suite()

assert report.mismatched_cases == 0
```

The default suite covers dynamic login, slow-loading recovery, retry recovery, approval-required actions, fixed-script contrast, and memory-related cases.

## Trace Export

```python
from mobiflow_agent import ExecutionTraceExporter

markdown = ExecutionTraceExporter().export_markdown(session)
json_payload = ExecutionTraceExporter().export_json(session)
```

The exported trace includes plan, role requests/results, step decisions, action traces, verifier verdicts, recovery outcomes, memory writeback, model trace refs, and a node-level timeline. Sensitive fields such as prompts, tokens, secrets, passwords, and provider responses are redacted.

## Memory / RAG Boundary

Task memory is not a raw log store. Records carry applicability context, confidence score, feedback, evidence refs, quality decisions, and governance state. Retrieval can combine deterministic matching and optional vector search, but the default local setup works without an external vector database.

## Run Tests

```powershell
cd MobiFlow_Agent
python -m pytest -q
```

Current expected baseline:

```text
416 passed
```

## Boundaries

- No distributed worker, queue, or daemon in this subproject.
- No real-device ADB loop in the Agent tests.
- No direct model-to-tool execution. Model output must become structured decisions or proposals and pass system validation.
- No claim of a general-purpose phone-control Agent. This is an execution-oriented Agent runtime prototype for bounded mobile experiment workflows.
