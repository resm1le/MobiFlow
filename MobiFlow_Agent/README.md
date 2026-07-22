# MobiFlow Agent

MobiFlow Agent is the task-first decision and orchestration layer of MobiFlow. It targets mobile workflows that cannot be handled reliably by a fixed script: permission dialogs, slow loading pages, wrong-page transitions, approval-required actions, and recoverable UI drift.

## Current Status

- Main runtime: `TaskGraphRuntime`, backed by LangGraph.
- Compatibility name: `TaskOrchestratorService`, graph-backed.
- Current verified test baseline: run `python -m pytest -q` in this subproject.
- Scope: Agent runtime, simulation, memory, evaluation, and traceability. Real-device execution remains outside this subproject.

## Core Workflow

```text
natural language task
  -> task intake / interpreter
  -> dynamic plan
  -> dynamic_observe
  -> decide_step
  -> dynamic_execute
  -> verify
  -> recover / replan if needed
  -> memory writeback
  -> trace export
```

`PlannerAgent` now always produces dynamic phase steps. `TaskStepKind` exposes `DYNAMIC` and `RECOVER`; verification remains a fixed graph evidence gate, not a user-visible plan step type. `TaskSession` remains the authoritative business state. LangGraph state only carries orchestration control fields.

## Recent Agent Enhancements

- Model-driven `StepPolicyAgent` with bounded `StepDecision` output.
- `StepPolicyDecisionValidator` for tool allowlist, target alignment, decision consistency, and evidence readiness.
- Structured `VerificationPredicate` support for success checks.
- Structured `blocked_checks` and verifier diagnostics for permission dialogs, wrong pages, loading screens, and other negative states.
- Observable step-policy validation payloads, so rejected model decisions show their issues and fallback decision in trace output.
- Typed verifier diagnostics and standardized mobile observation summaries for screen, loading, blocked, and visible-node state.
- Dynamic recovery scenarios, including slow-loading retry and fixed-script contrast.
- Task memory applicability, confidence scoring, feedback, risk isolation, and retrieval explanations.
- `ExecutionTraceExporter` with JSON, Markdown, redaction, file export, and node-level timeline output.
- Scenario regression suite grouped by normal, recovery, approval, fixed-script contrast, and memory capabilities, with report export.
- `TaskIntakeService` and `TaskInterpreter` for converting bounded natural-language mobile goals into validated dynamic task sessions.
- Versioned `SequenceCatalog` resolution and model-assisted, human-reviewed `SequenceDraftService` waypoint drafts.
- Governed heterogeneous collection dispatch from bounded natural language or a typed `DispatchPlan`.

## Package Responsibilities

```text
mobiflow_agent/
  graph/        LangGraph runtime, nodes, routes, and graph support ops
  intake/       task interpreter, scenario templates, validation, verification spec factory
  agents/       planner, observer, step policy, executor, verifier, recovery
  task/         TaskSession, TaskPlan, TaskStep, task status models
  runtime/      harness, checkpointing, context compression, trace export
  memory/       task memory records, retrieval, quality, governance, feedback
  evaluation/   simulation scenarios, quality gates, regression suite
  platform/     simulated mobile adapter and platform contracts
  model/        provider-agnostic generation and embedding runtime
  control/      dispatcher, policy, and compatibility imports
  waypoint/     waypoint models, compiler, packaged sequence catalog, and drafting service
  collection/   bounded intent planning, dispatch validation/compilation, and governed submission
  common/       canonical contracts and id helpers
```

## Minimal Runtime Example

```python
from mobiflow_agent import EntityKind, TaskGraphRuntime, VerificationCheck, VerificationSpec

runtime = TaskGraphRuntime()

session = runtime.create_session(
    "Login to the demo app using bounded mobile UI actions.",
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

## Natural Language Intake

```python
from mobiflow_agent import TaskIntakeService, TaskGraphRuntime

runtime = TaskGraphRuntime()
intake = TaskIntakeService(runtime=runtime)

# New: compile a natural-language regression TestCase (model-runtime backed).
result = intake.submit_test_case("Log out and confirm the login button disappears.")

# Legacy template-bounded path (still supported):
legacy = intake.create_session_from_text("登录 demo app 并验证进入首页")

if result.session is not None:
    completed = runtime.run(result.session)
```

`submit_test_case` runs the four-stage pipeline (`TestCaseParser → TestCaseValidator → AssertionSynthesizer → TestCaseAssembler`) to compile prose into a `TestCase` and a `VerificationSpec`. Synthesized assertions are confined to the six-member predicate vocabulary (`exists, not_exists, equals, contains, any_equals, any_contains`) over the simulation fact catalog (`mobile_observation_summary`, `simulated_screen_snapshot`, `simulated_ui_tree`); out-of-vocabulary assertions are rejected and retried once before asking for clarification. Real-device observation-fact enrichment is a separate follow-up. `create_session_from_text` remains the template-bounded path for the demo login, permission popup contrast, slow-loading recovery, and approval-required destructive-action scenarios.

## Waypoint Sequence Catalog and Drafting

```python
from mobiflow_agent.waypoint import (
    SequenceCatalog,
    SequenceDraftRequest,
    SequenceDraftService,
)

catalog = SequenceCatalog.default()
sequence = catalog.resolve_sequence("wechat.text_chat.v1")

draft_service = SequenceDraftService(model_runtime=configured_model_runtime)
result = draft_service.draft_sequence(
    SequenceDraftRequest(
        source_text="Open WeChat, reach the home screen, then open the target chat.",
        sequence_id="wechat.text_chat.v2",
        behavior_label="wechat_text_chat",
        profile_package="com.tencent.mm",
    )
)
```

`SequenceCatalog` is a deterministic, read-only view of versioned JSON resources packaged with the Agent. Every resolve returns a deep copy, so caller mutation cannot change the catalog. `SequenceDraftService` requires a configured model runtime and reuses intake parsing plus per-waypoint assertion synthesis. A ready result is still only a draft: it must be reviewed and added as a versioned JSON file through normal code review. Drafting never writes the catalog, creates a session or run, calls Platform tools, or performs device actions.

## Governed Collection Dispatch

```python
from mobiflow_agent.collection import CollectionIntent

intent = CollectionIntent(
    raw_text="Run 3 text-chat collections on android13 devices.",
    labels=["pcap"],
)

# Read-only: discovery, bounded model planning, and deterministic compilation.
prepared = service.plan_intent(intent, caller_context)

# Submits the compiled create_heterogeneous_run proposal through Platform governance.
submitted = service.submit_intent(intent, caller_context)
```

`CollectionDispatchService` refreshes `list_devices` and `get_run_planning_catalog` on every call, resolves each versioned sequence from the Agent catalog, and compiles a complete P2-2 payload. It never calls `create_heterogeneous_run` directly. `submit_intent` passes the underlying action through `propose_governed_action`; `submit_plan` provides the same governed path for an already structured plan and cannot bypass compiler validation.

`submitted.status == CollectionDispatchStatus.APPROVAL_REQUIRED` is an expected governance state—not a failure and not evidence that a run exists. The caller must display the returned confirmation details and pass the user's explicit decision to the existing Platform adapter `resolve_approval(...)` method. The collection service does not auto-approve confirmations. Device availability and tag-capacity warnings describe a discovery snapshot only; Platform validates and reserves devices authoritatively after approval.

Production task execution starts only after a device Executor claims the Platform task. The Agent does not receive or store Platform `runTargetId`/`attemptId` in `TaskSession` or drive the attempt lifecycle. Platform owns approval, scheduling, lineage, aggregate state, and evidence persistence; the authenticated Executor owns start/events/finish and waypoint evidence publication. `ExecutionTraceExporter` waypoint data remains simulation/diagnostic evidence and must not be presented as real-device evidence.

The repository's signed mock Executor can validate this control-plane contract without a device. It reads all task and attempt identity from claim responses and clearly reports `SIMULATED EXECUTOR - NO DEVICE UI EXECUTED`; it does not validate Android profiles or real App behavior.

## Scenario Regression Suite

```python
from mobiflow_agent import ScenarioRegressionSuiteRunner

report = ScenarioRegressionSuiteRunner().run_default_suite()

assert report.mismatched_cases == 0
```

The default suite covers dynamic login, slow-loading recovery, retry recovery, approval-required actions, fixed-script contrast, and memory-related cases. Fixed scripts are kept only as an evaluation baseline, not as an Agent runtime plan mode.

Generate a demo report from the module CLI:

```powershell
python -m mobiflow_agent.evaluation.scenario.suite --format markdown --output .test-artifacts/scenario-report.md
```

## Trace Export

```python
from mobiflow_agent import ExecutionTraceExporter

markdown = ExecutionTraceExporter().export_markdown(session)
json_payload = ExecutionTraceExporter().export_json(session)
ExecutionTraceExporter().write_markdown(session, ".test-artifacts/trace.md")
ExecutionTraceExporter().write_json(session, ".test-artifacts/trace.json")
```

The exported trace includes plan, role requests/results, step decisions, decision validation, rejected model decisions, fallback decisions, action traces, verifier verdicts, recovery outcomes, memory highlights and risk reasons, memory writeback, model trace refs, and a node-level timeline. Sensitive fields such as prompts, tokens, secrets, passwords, and provider responses are redacted.

## Memory / RAG Boundary

Task memory is not a raw log store. Records carry applicability context, confidence score, feedback, risk signals, evidence refs, quality decisions, and governance state. Retrieval can combine deterministic matching and optional vector search, but the default local setup works without an external vector database.

## Run Tests

```powershell
cd MobiFlow_Agent
python -m pytest -q
```

## Boundaries

- No distributed worker, queue, or daemon in this subproject.
- No real-device ADB loop in the Agent tests.
- No Platform attempt lifecycle inside the Agent TaskGraph; production attempts belong to Platform and Executor.
- No direct model-to-tool execution. Model output must become structured decisions or proposals and pass system validation.
- No claim of a general-purpose phone-control Agent. This is an execution-oriented Agent runtime prototype for bounded mobile experiment workflows.
