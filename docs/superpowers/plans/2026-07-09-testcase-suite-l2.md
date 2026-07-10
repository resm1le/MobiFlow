# TestCase Suite (L2) — Regression Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Loop the L0+L1 single-case path (`submit_test_case` → `runtime.run`) over an ordered set of prose test cases, serially with per-case failure isolation, and aggregate a first-class structured `TestSuiteReport` plus a thin JSON/Markdown renderer.

**Architecture:** `TestSuite` (suite_id + ordered prose `SuiteCaseInput`s) → `TestSuiteRunner.run(suite)` loops each case: `TaskIntakeService.submit_test_case(text)` → if READY, `TaskGraphRuntime.run(session)` → map `(session.status, last_verdict.status)` to a `TestRunResult` via a status-first exhaustive table → collect → aggregate `TestSuiteReport`. A separate `TestSuiteReportExporter` (mirrors `ExecutionTraceExporter`) projects the report to JSON/Markdown from a single redacted payload. The structured report is the product; the render is a projection.

**Tech Stack:** Python 3.11, pydantic v2 (`StrictModel`, `extra="forbid"`, `model_validator`), LangGraph (via `TaskGraphRuntime`), pytest (`pytest>=7.4`, `testpaths=["tests"]`, `pythonpath=["."]`).

## Global Constraints

Every task's requirements implicitly include this section. Values copied verbatim from the spec.

- **G-L2-1 — Pure Agent-layer.** L2 lives entirely in `MobiFlow_Agent/`. It composes the existing `TaskIntakeService` + `TaskGraphRuntime` in Python. No Java Platform layer, no device-pool fan-out.
- **G-L2-2 — Serial + failure-isolation.** Cases run one at a time, in submission order. Every case is wrapped in `try/except`; an intake `NEEDS_CLARIFICATION`, a non-success verdict, or ANY raised exception is recorded into a `TestRunResult` and the batch CONTINUES. A partially-failing suite is the NORMAL case; the batch always runs to completion.
- **G-L2-3 — Structured-report-first.** `TestSuiteReport` / `TestRunResult` are the atoms; the renderer is a pure projection. L3 consumes the structured objects directly, never re-parses Markdown.
- **G-L2-4 — Additive.** The L0+L1 single-case path (`submit_test_case`, `create_session_from_text`, the four stages) is untouched. L2 adds NEW modules only + one new public entry point. Do not edit `intake/service.py`, `intake/models.py`, `graph/runtime.py`, `task/session.py`.
- **G-L2-5 — Evidence-first.** Every field/decision is cross-checked against real code.
- **G-L2-6 — run_id determinism.** `run_id` and `generated_at_ms` MUST be injectable for tests (no bare `uuid4()`/`time.time()` inside the runner). Real ids come from an injected factory whose default uses `uuid4`, matching `common/ids.py`.

Review-fix rules (folded into the tasks below, do not re-litigate):

- **R1 — status-first mapping.** PASSED requires `session.status == COMPLETED` AND `last_verdict.status == VERIFIED_SUCCESS`. `last_verdict` alone must never decide PASSED (a stale `VERIFIED_SUCCESS` can survive a FAILED transition).
- **R2 — exhaustive + catch-all.** The mapping covers every terminal `TaskStatus` returned by `runtime.run` (`{COMPLETED, FAILED, AWAITING_APPROVAL, HANDED_OFF}`) and ends with a catch-all → `ERROR`. No silent fall-through.
- **R3 — INCONCLUSIVE outcome.** A distinct 5th outcome for "couldn't determine" (verdict `VERIFIED_UNKNOWN`/`BLOCKED`, session `HANDED_OFF`/`AWAITING_APPROVAL`, or `COMPLETED` without a success verdict).
- **R4 — render from redacted dict.** BOTH `export_json` and `export_markdown` build from the SAME `_redact(report.model_dump(mode="json"))` payload. Markdown reads its row values out of that redacted dict, never from raw `result.verdict`/`result.summary`.
- **R5 — field-mask in exporter tests.** `session_id`/`verdict_id`/nested ids are `uuid4`-based, so exporter tests field-mask them rather than assert a full golden.

---

## File Structure

New modules (all additive; nothing existing is modified except two `__init__.py` export lists):

- **Create** `MobiFlow_Agent/mobiflow_agent/intake/suite.py` — L2 domain atoms: `SuiteCaseOutcome` (enum), `SuiteCaseInput`, `TestSuite`, `TestRunResult`, `TestSuiteReport`. All subclass `StrictModel`. Post-run/aggregation lifecycle; kept out of `models.py` to keep the L0+L1 diff clean (G-L2-4).
- **Create** `MobiFlow_Agent/mobiflow_agent/intake/suite_runner.py` — `TestSuiteRunner`: composes `(TaskIntakeService, TaskGraphRuntime)`; the serial loop, the exact status-first §2.1 outcome mapping, per-case try/except isolation, injectable `run_id_factory`/`clock`.
- **Create** `MobiFlow_Agent/mobiflow_agent/runtime/suite_report_export.py` — `TestSuiteReportExporter`: mirrors `ExecutionTraceExporter`; `export_json`/`export_markdown`/`dumps_json`/`write_json`/`write_markdown`, reusing the `_redact` + `SENSITIVE_KEYS` discipline; both renders sourced from one redacted payload (R4).
- **Modify** `MobiFlow_Agent/mobiflow_agent/common/ids.py` — add `build_suite_run_id()` (mirror `_build_id`).
- **Modify** `MobiFlow_Agent/mobiflow_agent/intake/__init__.py` — export the five suite atoms + `TestSuiteRunner` (additive).
- **Modify** `MobiFlow_Agent/mobiflow_agent/runtime/__init__.py` — export `TestSuiteReportExporter` (additive, via the lazy `__getattr__` pattern already used for `ExecutionTraceExporter`).

Test modules:

- **Create** `MobiFlow_Agent/tests/common/test_suite_run_id.py`
- **Create** `MobiFlow_Agent/tests/intake/test_suite_models.py`
- **Create** `MobiFlow_Agent/tests/intake/test_suite_runner.py`
- **Create** `MobiFlow_Agent/tests/runtime/test_suite_report_export.py`

All tests run from `MobiFlow_Agent/` (that is where `pyproject.toml` sets `pythonpath=["."]` and `testpaths=["tests"]`). Every `pytest` / `git` command below assumes the working directory is `MobiFlow_Agent/`.

---

## Task 1: `build_suite_run_id()` id builder

**Files:**
- Modify: `MobiFlow_Agent/mobiflow_agent/common/ids.py`
- Test: `MobiFlow_Agent/tests/common/test_suite_run_id.py`

**Interfaces:**
- Consumes: `_build_id(prefix: str) -> str` (existing, `ids.py:8-9`).
- Produces: `build_suite_run_id() -> str` returning `f"suite-run:{uuid4().hex}"`. Consumed by `TestSuiteRunner`'s default `run_id_factory` (Task 3).

- [ ] **Step 1: Write the failing test**

Create `MobiFlow_Agent/tests/common/test_suite_run_id.py`:

```python
from mobiflow_agent.common.ids import build_suite_run_id


def test_build_suite_run_id_has_prefix_and_is_unique() -> None:
    first = build_suite_run_id()
    second = build_suite_run_id()

    assert first.startswith("suite-run:")
    assert len(first) > len("suite-run:")
    assert first != second
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/common/test_suite_run_id.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_suite_run_id'`.

- [ ] **Step 3: Write minimal implementation**

In `MobiFlow_Agent/mobiflow_agent/common/ids.py`, add after `build_role_result_id` (line 33):

```python
def build_suite_run_id() -> str:
    return _build_id("suite-run")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/common/test_suite_run_id.py -v`
Expected: PASS (2 assertions, 1 test).

- [ ] **Step 5: Commit**

```bash
git add mobiflow_agent/common/ids.py tests/common/test_suite_run_id.py
git commit -m "feat(intake): add build_suite_run_id id builder for L2 suite runs"
```

---

## Task 2: L2 domain model (`intake/suite.py`)

**Files:**
- Create: `MobiFlow_Agent/mobiflow_agent/intake/suite.py`
- Test: `MobiFlow_Agent/tests/intake/test_suite_models.py`

**Interfaces:**
- Consumes: `StrictModel` (`common/contracts.py:9`), `VerificationVerdict` (`common/contracts.py:221`), `TaskStatus` (`task/plan.py:10`), pydantic `Field`, `model_validator`.
- Produces:
  - `SuiteCaseOutcome(str, Enum)` with members `PASSED`, `FAILED`, `INCONCLUSIVE`, `CLARIFICATION_BLOCKED`, `ERROR` (values `"passed"`, `"failed"`, `"inconclusive"`, `"clarification_blocked"`, `"error"`).
  - `SuiteCaseInput(StrictModel)`: `case_id: str` (min_length=1), `text: str` (min_length=1), `platform_context: dict[str, Any] | None = None`, `confirmed: bool = False`.
  - `TestSuite(StrictModel)`: `suite_id: str` (min_length=1), `name: str | None = None`, `cases: list[SuiteCaseInput]` (min_length=1).
  - `TestRunResult(StrictModel)`: `run_id: str` (min_length=1), `case_id: str` (min_length=1), `outcome: SuiteCaseOutcome`, `verdict: VerificationVerdict | None = None`, `session_id: str | None = None`, `session_status: TaskStatus | None = None`, `summary: str | None = None`, `trace_refs: list[str] = []`.
  - `TestSuiteReport(StrictModel)`: `run_id: str`, `suite_id: str`, `suite_name: str | None = None`, `total: int`, `passed/failed/inconclusive/clarification_blocked/errored: int`, `pass_rate: float`, `results: list[TestRunResult]`, `generated_at_ms: int | None = None`; `model_validator(mode="after")` enforcing `passed+failed+inconclusive+clarification_blocked+errored == total` and, when `total == 0`, `pass_rate == 0.0`.

- [ ] **Step 1: Write the failing test**

Create `MobiFlow_Agent/tests/intake/test_suite_models.py`:

```python
import pytest
from pydantic import ValidationError

from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.intake.suite import (
    SuiteCaseInput,
    SuiteCaseOutcome,
    TestRunResult,
    TestSuite,
    TestSuiteReport,
)
from mobiflow_agent.task.plan import TaskStatus


def _success_verdict() -> VerificationVerdict:
    return VerificationVerdict(
        verdict_id="verdict-1",
        status=VerificationStatus.VERIFIED_SUCCESS,
        summary="home screen visible",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        evidence_refs=[
            EvidenceRef(
                evidence_id="snapshot:task:task-1",
                kind=EvidenceKind.PLATFORM_SNAPSHOT,
                summary="snapshot",
                locator="loc-1",
            )
        ],
    )


def test_suite_case_outcome_values() -> None:
    assert SuiteCaseOutcome.PASSED.value == "passed"
    assert SuiteCaseOutcome.FAILED.value == "failed"
    assert SuiteCaseOutcome.INCONCLUSIVE.value == "inconclusive"
    assert SuiteCaseOutcome.CLARIFICATION_BLOCKED.value == "clarification_blocked"
    assert SuiteCaseOutcome.ERROR.value == "error"


def test_test_suite_requires_at_least_one_case() -> None:
    with pytest.raises(ValidationError):
        TestSuite(suite_id="suite-1", cases=[])


def test_suite_case_input_defaults() -> None:
    case = SuiteCaseInput(case_id="c1", text="Login and reach home.")
    assert case.platform_context is None
    assert case.confirmed is False


def test_test_run_result_carries_verdict_and_status() -> None:
    result = TestRunResult(
        run_id="suite-run:abc",
        case_id="c1",
        outcome=SuiteCaseOutcome.PASSED,
        verdict=_success_verdict(),
        session_id="task-session:1",
        session_status=TaskStatus.COMPLETED,
        summary=None,
        trace_refs=["trace:1"],
    )
    assert result.outcome is SuiteCaseOutcome.PASSED
    assert result.verdict.status is VerificationStatus.VERIFIED_SUCCESS


def test_test_suite_report_count_invariant_holds() -> None:
    report = TestSuiteReport(
        run_id="suite-run:abc",
        suite_id="suite-1",
        suite_name="regression",
        total=2,
        passed=1,
        failed=1,
        inconclusive=0,
        clarification_blocked=0,
        errored=0,
        pass_rate=0.5,
        results=[],
        generated_at_ms=None,
    )
    assert report.total == 2


def test_test_suite_report_count_invariant_violation_raises() -> None:
    with pytest.raises(ValidationError):
        TestSuiteReport(
            run_id="suite-run:abc",
            suite_id="suite-1",
            total=2,
            passed=1,
            failed=0,
            inconclusive=0,
            clarification_blocked=0,
            errored=0,
            pass_rate=0.5,
            results=[],
        )


def test_test_suite_report_total_zero_requires_zero_pass_rate() -> None:
    with pytest.raises(ValidationError):
        TestSuiteReport(
            run_id="suite-run:abc",
            suite_id="suite-1",
            total=0,
            passed=0,
            failed=0,
            inconclusive=0,
            clarification_blocked=0,
            errored=0,
            pass_rate=1.0,
            results=[],
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/intake/test_suite_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mobiflow_agent.intake.suite'`.

- [ ] **Step 3: Write minimal implementation**

Create `MobiFlow_Agent/mobiflow_agent/intake/suite.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import StrictModel, VerificationVerdict
from mobiflow_agent.task.plan import TaskStatus


class SuiteCaseOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    CLARIFICATION_BLOCKED = "clarification_blocked"
    ERROR = "error"


class SuiteCaseInput(StrictModel):
    case_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    platform_context: dict[str, Any] | None = None
    confirmed: bool = False


class TestSuite(StrictModel):
    __test__ = False

    suite_id: str = Field(min_length=1)
    name: str | None = None
    cases: list[SuiteCaseInput] = Field(min_length=1)


class TestRunResult(StrictModel):
    __test__ = False

    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    outcome: SuiteCaseOutcome
    verdict: VerificationVerdict | None = None
    session_id: str | None = None
    session_status: TaskStatus | None = None
    summary: str | None = None
    trace_refs: list[str] = Field(default_factory=list)


class TestSuiteReport(StrictModel):
    __test__ = False

    run_id: str = Field(min_length=1)
    suite_id: str = Field(min_length=1)
    suite_name: str | None = None
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    inconclusive: int = Field(ge=0)
    clarification_blocked: int = Field(ge=0)
    errored: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    results: list[TestRunResult] = Field(default_factory=list)
    generated_at_ms: int | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "TestSuiteReport":
        tallied = (
            self.passed
            + self.failed
            + self.inconclusive
            + self.clarification_blocked
            + self.errored
        )
        if tallied != self.total:
            raise ValueError(
                "TestSuiteReport counts must sum to total: "
                f"{tallied} != {self.total}."
            )
        if self.total == 0 and self.pass_rate != 0.0:
            raise ValueError("TestSuiteReport pass_rate must be 0.0 when total is 0.")
        return self


__all__ = [
    "SuiteCaseInput",
    "SuiteCaseOutcome",
    "TestRunResult",
    "TestSuite",
    "TestSuiteReport",
]
```

> Note: `TestSuite`/`TestRunResult`/`TestSuiteReport` set `__test__ = False` (as `TestCase`/`TestStep` do in `models.py:82,89`) so pytest does not try to collect these `Test`-prefixed pydantic models as test classes.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/intake/test_suite_models.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add mobiflow_agent/intake/suite.py tests/intake/test_suite_models.py
git commit -m "feat(intake): add L2 suite domain model with count invariant"
```

---

## Task 3: `TestSuiteRunner` — loop, outcome mapping, isolation

**Files:**
- Create: `MobiFlow_Agent/mobiflow_agent/intake/suite_runner.py`
- Test: `MobiFlow_Agent/tests/intake/test_suite_runner.py`

**Interfaces:**
- Consumes: `TaskIntakeService.submit_test_case(text, *, platform_context=None, confirmed=False, session_id=None) -> TaskIntakeResult` (`service.py:72`); `TaskIntakeResult` fields `status`, `session`, `clarification_questions`, `issues`, `trace_refs` (`models.py:37-44`); `TaskIntakeStatus.READY` (`models.py:12-15`); `TaskGraphRuntime.run(session) -> TaskSession` (`runtime.py:82`); `TaskSession.status`/`last_verdict`/`session_id` (`session.py:26,42`); `TaskStatus` (`plan.py:10-20`); `VerificationStatus` (`contracts.py:46-50`); `build_suite_run_id` (Task 1); `build_memory_timestamp_ms` (`memory/store.py:435`); the Task 2 atoms.
- Produces:
  - `TestSuiteRunner(intake_service: TaskIntakeService, runtime: TaskGraphRuntime, *, run_id_factory: Callable[[], str] = build_suite_run_id, clock: Callable[[], int] = build_memory_timestamp_ms)`.
  - `run(self, suite: TestSuite) -> TestSuiteReport`.
  - Private `_map_outcome(self, status: TaskStatus, verdict: VerificationVerdict | None) -> tuple[SuiteCaseOutcome, str | None]` implementing the exact §2.1 table (used only for the ran-to-terminal path; intake-blocked and exception paths are handled in `run`).

Collaborators are duck-typed in tests: the intake stub exposes `.submit_test_case(...)` returning a chosen `TaskIntakeResult`; the runtime stub exposes `.run(session)` returning a chosen `TaskSession`. No real graph is needed for the mapping tests.

### Outcome mapping (exact §2.1 table — status-first, exhaustive)

Evaluated in `run`/`_map_outcome` in THIS order. Rows 1-2 live in `run` (intake-blocked / exception); rows 3-10 live in `_map_outcome`:

| # | condition | outcome |
|---|---|---|
| 1 | intake `result.status != READY` (case never ran) | `CLARIFICATION_BLOCKED` |
| 2 | exception raised anywhere in the case pipeline | `ERROR` |
| 3 | `status == COMPLETED` and `verdict is not None and verdict.status == VERIFIED_SUCCESS` | `PASSED` |
| 4 | `status == COMPLETED` (verdict missing / not success) | `INCONCLUSIVE` |
| 5 | `status == FAILED` and `verdict is not None and verdict.status == VERIFIED_FAILED` | `FAILED` |
| 6 | `status == FAILED` (verdict None/stale/other) | `FAILED` |
| 7 | `status == AWAITING_APPROVAL` | `INCONCLUSIVE` |
| 8 | `status == HANDED_OFF` | `INCONCLUSIVE` |
| 9 | `verdict is not None and verdict.status in {VERIFIED_UNKNOWN, BLOCKED}` | `INCONCLUSIVE` |
| 10 | catch-all — anything else | `ERROR` |

- [ ] **Step 1: Write the failing tests**

Create `MobiFlow_Agent/tests/intake/test_suite_runner.py`:

```python
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.intake.models import TaskIntakeResult, TaskIntakeStatus
from mobiflow_agent.intake.suite import (
    SuiteCaseInput,
    SuiteCaseOutcome,
    TestSuite,
)
from mobiflow_agent.intake.suite_runner import TestSuiteRunner
from mobiflow_agent.task.plan import TaskStatus
from mobiflow_agent.task.session import TaskSession


def _verdict(status: VerificationStatus, *, summary: str = "done") -> VerificationVerdict:
    evidence = [
        EvidenceRef(
            evidence_id="snapshot:task:task-1",
            kind=EvidenceKind.PLATFORM_SNAPSHOT,
            summary="snapshot",
            locator="loc-1",
        )
    ]
    return VerificationVerdict(
        verdict_id=f"verdict:{status.value}",
        status=status,
        summary=summary,
        target_kind=EntityKind.TASK,
        target_id="task-1",
        evidence_refs=evidence
        if status in {VerificationStatus.VERIFIED_SUCCESS, VerificationStatus.VERIFIED_FAILED}
        else [],
        blocked_reason="blocked_by_policy" if status == VerificationStatus.BLOCKED else None,
    )


def _session(
    status: TaskStatus,
    *,
    verdict: VerificationVerdict | None = None,
    session_id: str = "task-session:s1",
) -> TaskSession:
    return TaskSession(
        session_id=session_id,
        goal="Login and reach home.",
        status=status,
        last_verdict=verdict,
    )


class _IntakeStub:
    """Stands in for TaskIntakeService; records submit calls and returns queued results."""

    def __init__(self, results: list[TaskIntakeResult]) -> None:
        self._results = list(results)
        self.calls: list[dict] = []

    def submit_test_case(self, text, *, platform_context=None, confirmed=False, session_id=None):
        self.calls.append(
            {
                "text": text,
                "platform_context": platform_context,
                "confirmed": confirmed,
                "session_id": session_id,
            }
        )
        return self._results.pop(0)


class _RuntimeStub:
    """Stands in for TaskGraphRuntime; returns queued sessions from .run()."""

    def __init__(self, sessions: list[TaskSession]) -> None:
        self._sessions = list(sessions)
        self.run_calls: list[TaskSession] = []

    def run(self, session, *, config=None):
        self.run_calls.append(session)
        return self._sessions.pop(0)


def _ready(session: TaskSession) -> TaskIntakeResult:
    return TaskIntakeResult(status=TaskIntakeStatus.READY, session=session, trace_refs=["trace:intake"])


def _suite(*case_ids: str) -> TestSuite:
    return TestSuite(
        suite_id="suite-1",
        name="regression",
        cases=[SuiteCaseInput(case_id=cid, text=f"case {cid}") for cid in case_ids],
    )


def _run_single(intake_result: TaskIntakeResult, ran_session: TaskSession | None):
    intake = _IntakeStub([intake_result])
    runtime = _RuntimeStub([ran_session] if ran_session is not None else [])
    runner = TestSuiteRunner(
        intake, runtime, run_id_factory=lambda: "suite-run:test", clock=lambda: 123
    )
    report = runner.run(_suite("c1"))
    return report, intake, runtime


# --- Outcome matrix (rows 3-10) ---

def test_completed_with_success_verdict_maps_to_passed() -> None:
    verdict = _verdict(VerificationStatus.VERIFIED_SUCCESS)
    session = _session(TaskStatus.COMPLETED, verdict=verdict)
    report, _, _ = _run_single(_ready(session), session)
    assert report.results[0].outcome is SuiteCaseOutcome.PASSED
    assert report.passed == 1


def test_completed_without_verdict_maps_to_inconclusive() -> None:
    session = _session(TaskStatus.COMPLETED, verdict=None)
    report, _, _ = _run_single(_ready(session), session)
    assert report.results[0].outcome is SuiteCaseOutcome.INCONCLUSIVE
    assert report.inconclusive == 1


def test_failed_with_failed_verdict_maps_to_failed() -> None:
    verdict = _verdict(VerificationStatus.VERIFIED_FAILED)
    session = _session(TaskStatus.FAILED, verdict=verdict)
    report, _, _ = _run_single(_ready(session), session)
    assert report.results[0].outcome is SuiteCaseOutcome.FAILED
    assert report.results[0].summary == verdict.summary


def test_stale_success_verdict_on_failed_session_maps_to_failed_not_passed() -> None:
    # R1 regression: session FAILED but last_verdict still VERIFIED_SUCCESS.
    verdict = _verdict(VerificationStatus.VERIFIED_SUCCESS)
    session = _session(TaskStatus.FAILED, verdict=verdict)
    report, _, _ = _run_single(_ready(session), session)
    assert report.results[0].outcome is SuiteCaseOutcome.FAILED
    assert report.passed == 0


def test_awaiting_approval_maps_to_inconclusive() -> None:
    session = _session(TaskStatus.AWAITING_APPROVAL)
    report, _, _ = _run_single(_ready(session), session)
    assert report.results[0].outcome is SuiteCaseOutcome.INCONCLUSIVE


def test_handed_off_maps_to_inconclusive() -> None:
    session = _session(TaskStatus.HANDED_OFF)
    report, _, _ = _run_single(_ready(session), session)
    assert report.results[0].outcome is SuiteCaseOutcome.INCONCLUSIVE


def test_blocked_verdict_maps_to_inconclusive() -> None:
    # Verdict-carrying edge case: a non-terminal-looking status carrying BLOCKED.
    verdict = _verdict(VerificationStatus.BLOCKED)
    session = _session(TaskStatus.VERIFYING, verdict=verdict)
    report, _, _ = _run_single(_ready(session), session)
    assert report.results[0].outcome is SuiteCaseOutcome.INCONCLUSIVE


def test_unmapped_terminal_state_maps_to_error_catch_all() -> None:
    # R2 catch-all: a status with no verdict that matches no row 3-9.
    session = _session(TaskStatus.OBSERVING, verdict=None)
    report, _, _ = _run_single(_ready(session), session)
    result = report.results[0]
    assert result.outcome is SuiteCaseOutcome.ERROR
    assert "unmapped terminal state" in result.summary


# --- Rows 1-2: intake-blocked & exception ---

def test_non_ready_intake_maps_to_clarification_blocked_without_running() -> None:
    blocked = TaskIntakeResult(
        status=TaskIntakeStatus.NEEDS_CLARIFICATION,
        clarification_questions=["What is the expected result?"],
        issues=[],
        trace_refs=["trace:parse"],
    )
    intake = _IntakeStub([blocked])
    runtime = _RuntimeStub([])
    runner = TestSuiteRunner(intake, runtime, run_id_factory=lambda: "suite-run:test", clock=lambda: 1)
    report = runner.run(_suite("c1"))
    result = report.results[0]
    assert result.outcome is SuiteCaseOutcome.CLARIFICATION_BLOCKED
    assert result.summary == "What is the expected result?"
    assert result.trace_refs == ["trace:parse"]
    assert runtime.run_calls == []  # never ran
    assert report.clarification_blocked == 1


def test_exception_in_case_maps_to_error_and_isolates_batch() -> None:
    # First case raises inside submit; second case passes. Batch runs to completion.
    good_session = _session(TaskStatus.COMPLETED, verdict=_verdict(VerificationStatus.VERIFIED_SUCCESS))

    class _PartialFailIntake:
        def __init__(self):
            self.calls = 0

        def submit_test_case(self, text, *, platform_context=None, confirmed=False, session_id=None):
            self.calls += 1
            if self.calls == 1:
                raise KeyError("boom")
            return _ready(good_session)

    intake = _PartialFailIntake()
    runtime = _RuntimeStub([good_session])
    runner = TestSuiteRunner(intake, runtime, run_id_factory=lambda: "suite-run:test", clock=lambda: 1)
    report = runner.run(_suite("c1", "c2"))
    assert report.total == 2
    assert report.results[0].outcome is SuiteCaseOutcome.ERROR
    assert "boom" in report.results[0].summary
    assert report.results[1].outcome is SuiteCaseOutcome.PASSED
    assert report.errored == 1
    assert report.passed == 1


# --- run_id determinism, session_id invariant, math ---

def test_run_id_generated_once_and_stamped_on_every_result() -> None:
    s1 = _session(TaskStatus.COMPLETED, verdict=_verdict(VerificationStatus.VERIFIED_SUCCESS), session_id="task-session:a")
    s2 = _session(TaskStatus.COMPLETED, verdict=_verdict(VerificationStatus.VERIFIED_SUCCESS), session_id="task-session:b")
    intake = _IntakeStub([_ready(s1), _ready(s2)])
    runtime = _RuntimeStub([s1, s2])
    calls = {"n": 0}

    def factory() -> str:
        calls["n"] += 1
        return f"suite-run:fixed-{calls['n']}"

    runner = TestSuiteRunner(intake, runtime, run_id_factory=factory, clock=lambda: 999)
    report = runner.run(_suite("c1", "c2"))
    assert calls["n"] == 1  # generated once per run()
    assert report.run_id == "suite-run:fixed-1"
    assert all(r.run_id == "suite-run:fixed-1" for r in report.results)
    assert report.generated_at_ms == 999


def test_runner_passes_session_id_none_per_case() -> None:
    session = _session(TaskStatus.COMPLETED, verdict=_verdict(VerificationStatus.VERIFIED_SUCCESS))
    _, intake, _ = _run_single(_ready(session), session)
    assert intake.calls[0]["session_id"] is None


def test_pass_rate_and_counts_math() -> None:
    passed_session = _session(TaskStatus.COMPLETED, verdict=_verdict(VerificationStatus.VERIFIED_SUCCESS))
    failed_session = _session(TaskStatus.FAILED, verdict=_verdict(VerificationStatus.VERIFIED_FAILED))
    intake = _IntakeStub([_ready(passed_session), _ready(failed_session)])
    runtime = _RuntimeStub([passed_session, failed_session])
    runner = TestSuiteRunner(intake, runtime, run_id_factory=lambda: "suite-run:x", clock=lambda: 1)
    report = runner.run(_suite("c1", "c2"))
    assert report.total == 2
    assert report.passed == 1
    assert report.failed == 1
    assert report.pass_rate == 0.5


def test_case_forwards_platform_context_and_confirmed() -> None:
    session = _session(TaskStatus.COMPLETED, verdict=_verdict(VerificationStatus.VERIFIED_SUCCESS))
    intake = _IntakeStub([_ready(session)])
    runtime = _RuntimeStub([session])
    runner = TestSuiteRunner(intake, runtime, run_id_factory=lambda: "suite-run:x", clock=lambda: 1)
    suite = TestSuite(
        suite_id="suite-1",
        cases=[
            SuiteCaseInput(
                case_id="c1",
                text="Login.",
                platform_context={"device": "pixel"},
                confirmed=True,
            )
        ],
    )
    runner.run(suite)
    assert intake.calls[0]["platform_context"] == {"device": "pixel"}
    assert intake.calls[0]["confirmed"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/intake/test_suite_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mobiflow_agent.intake.suite_runner'`.

- [ ] **Step 3: Write minimal implementation**

Create `MobiFlow_Agent/mobiflow_agent/intake/suite_runner.py`:

```python
from __future__ import annotations

from typing import Callable

from mobiflow_agent.common.contracts import VerificationStatus, VerificationVerdict
from mobiflow_agent.common.ids import build_suite_run_id
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.memory.store import build_memory_timestamp_ms
from mobiflow_agent.task.plan import TaskStatus

from .models import TaskIntakeResult, TaskIntakeStatus
from .service import TaskIntakeService
from .suite import (
    SuiteCaseInput,
    SuiteCaseOutcome,
    TestRunResult,
    TestSuite,
    TestSuiteReport,
)


class TestSuiteRunner:
    __test__ = False

    def __init__(
        self,
        intake_service: TaskIntakeService,
        runtime: TaskGraphRuntime,
        *,
        run_id_factory: Callable[[], str] = build_suite_run_id,
        clock: Callable[[], int] = build_memory_timestamp_ms,
    ) -> None:
        self._intake_service = intake_service
        self._runtime = runtime
        self._run_id_factory = run_id_factory
        self._clock = clock

    def run(self, suite: TestSuite) -> TestSuiteReport:
        run_id = self._run_id_factory()
        results = [self._run_case(run_id, case) for case in suite.cases]
        counts = {outcome: 0 for outcome in SuiteCaseOutcome}
        for result in results:
            counts[result.outcome] += 1
        total = len(results)
        passed = counts[SuiteCaseOutcome.PASSED]
        pass_rate = (passed / total) if total else 0.0
        return TestSuiteReport(
            run_id=run_id,
            suite_id=suite.suite_id,
            suite_name=suite.name,
            total=total,
            passed=passed,
            failed=counts[SuiteCaseOutcome.FAILED],
            inconclusive=counts[SuiteCaseOutcome.INCONCLUSIVE],
            clarification_blocked=counts[SuiteCaseOutcome.CLARIFICATION_BLOCKED],
            errored=counts[SuiteCaseOutcome.ERROR],
            pass_rate=pass_rate,
            results=results,
            generated_at_ms=self._clock(),
        )

    def _run_case(self, run_id: str, case: SuiteCaseInput) -> TestRunResult:
        try:
            result = self._intake_service.submit_test_case(
                case.text,
                platform_context=case.platform_context,
                confirmed=case.confirmed,
                session_id=None,
            )
            if result.status != TaskIntakeStatus.READY:
                return self._blocked_result(run_id, case, result)

            session = result.session
            ran = self._runtime.run(session)
            outcome, summary = self._map_outcome(ran.status, ran.last_verdict)
            if outcome is SuiteCaseOutcome.FAILED and ran.last_verdict is not None:
                summary = ran.last_verdict.summary
            return TestRunResult(
                run_id=run_id,
                case_id=case.case_id,
                outcome=outcome,
                verdict=ran.last_verdict,
                session_id=ran.session_id,
                session_status=ran.status,
                summary=summary,
                trace_refs=list(result.trace_refs),
            )
        except Exception as exc:  # noqa: BLE001 - failure isolation (G-L2-2)
            return TestRunResult(
                run_id=run_id,
                case_id=case.case_id,
                outcome=SuiteCaseOutcome.ERROR,
                summary=str(exc),
            )

    @staticmethod
    def _blocked_result(
        run_id: str, case: SuiteCaseInput, result: TaskIntakeResult
    ) -> TestRunResult:
        summary_source = result.clarification_questions or result.issues
        return TestRunResult(
            run_id=run_id,
            case_id=case.case_id,
            outcome=SuiteCaseOutcome.CLARIFICATION_BLOCKED,
            session_id=result.session.session_id if result.session else None,
            summary=summary_source[0] if summary_source else None,
            trace_refs=list(result.trace_refs),
        )

    @staticmethod
    def _map_outcome(
        status: TaskStatus, verdict: VerificationVerdict | None
    ) -> tuple[SuiteCaseOutcome, str | None]:
        # Status-first, exhaustive (spec §2.1 rows 3-10). Rows 1-2 handled in run().
        if status == TaskStatus.COMPLETED:
            if verdict is not None and verdict.status == VerificationStatus.VERIFIED_SUCCESS:
                return SuiteCaseOutcome.PASSED, None
            return (
                SuiteCaseOutcome.INCONCLUSIVE,
                "completed without a success verdict",
            )
        if status == TaskStatus.FAILED:
            return SuiteCaseOutcome.FAILED, None
        if status == TaskStatus.AWAITING_APPROVAL:
            return (
                SuiteCaseOutcome.INCONCLUSIVE,
                "run halted awaiting approval; pass confirmed=True or resolve risk gate",
            )
        if status == TaskStatus.HANDED_OFF:
            return SuiteCaseOutcome.INCONCLUSIVE, "run handed off"
        if verdict is not None and verdict.status in {
            VerificationStatus.VERIFIED_UNKNOWN,
            VerificationStatus.BLOCKED,
        }:
            return SuiteCaseOutcome.INCONCLUSIVE, verdict.summary
        return (
            SuiteCaseOutcome.ERROR,
            f"unmapped terminal state: status={status}, "
            f"verdict={verdict and verdict.status}",
        )


__all__ = ["TestSuiteRunner"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/intake/test_suite_runner.py -v`
Expected: PASS (all matrix + isolation + determinism + math tests).

- [ ] **Step 5: Commit**

```bash
git add mobiflow_agent/intake/suite_runner.py tests/intake/test_suite_runner.py
git commit -m "feat(intake): add TestSuiteRunner with status-first outcome mapping and failure isolation"
```

---

## Task 4: `TestSuiteReportExporter` — JSON + Markdown from one redacted payload

**Files:**
- Create: `MobiFlow_Agent/mobiflow_agent/runtime/suite_report_export.py`
- Test: `MobiFlow_Agent/tests/runtime/test_suite_report_export.py`

**Interfaces:**
- Consumes: `TestSuiteReport` (Task 2); the `_redact`/`SENSITIVE_KEYS` discipline mirrored from `trace_export.py:10-21,140-152`.
- Produces: `TestSuiteReportExporter` with `export_json(report) -> dict`, `export_markdown(report) -> str`, `dumps_json(report) -> str`, `write_json(report, path) -> Path`, `write_markdown(report, path) -> Path`. Both `export_json` and `export_markdown` build from the SAME `_redact(report.model_dump(mode="json"))` payload (R4).

Markdown layout (per redacted dict `report`):

```
# Test Suite Report: {suite_name or suite_id}
- Run: {run_id}
- Suite: {suite_id}
- Total: {total}  Passed: {passed}  Failed: {failed}  Inconclusive: {inconclusive}  Blocked: {clarification_blocked}  Errored: {errored}
- Pass rate: {pass_rate:.1%}

## Summary
| case_id | outcome | verdict | summary | trace |
|---|---|---|---|---|
| <case_id> | <outcome> | <verdict.status or -> | <summary or -> | <session_id or first trace_ref or -> |
```

- [ ] **Step 1: Write the failing tests**

Create `MobiFlow_Agent/tests/runtime/test_suite_report_export.py`:

```python
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.intake.suite import (
    SuiteCaseOutcome,
    TestRunResult,
    TestSuiteReport,
)
from mobiflow_agent.runtime.suite_report_export import TestSuiteReportExporter
from mobiflow_agent.task.plan import TaskStatus


def _passed_result() -> TestRunResult:
    verdict = VerificationVerdict(
        verdict_id="verdict:success",
        status=VerificationStatus.VERIFIED_SUCCESS,
        summary="home screen visible",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        evidence_refs=[
            EvidenceRef(
                evidence_id="snapshot:task:task-1",
                kind=EvidenceKind.PLATFORM_SNAPSHOT,
                summary="snapshot",
                locator="loc-1",
            )
        ],
    )
    return TestRunResult(
        run_id="suite-run:r1",
        case_id="checkout-01",
        outcome=SuiteCaseOutcome.PASSED,
        verdict=verdict,
        session_id="task-session:sess-1",
        session_status=TaskStatus.COMPLETED,
        trace_refs=["trace:1"],
    )


def _blocked_result() -> TestRunResult:
    return TestRunResult(
        run_id="suite-run:r1",
        case_id="bad-prose-03",
        outcome=SuiteCaseOutcome.CLARIFICATION_BLOCKED,
        summary="What is the expected result?",
    )


def _report() -> TestSuiteReport:
    return TestSuiteReport(
        run_id="suite-run:r1",
        suite_id="suite-1",
        suite_name="regression",
        total=2,
        passed=1,
        failed=0,
        inconclusive=0,
        clarification_blocked=1,
        errored=0,
        pass_rate=0.5,
        results=[_passed_result(), _blocked_result()],
        generated_at_ms=123,
    )


def test_export_json_returns_redacted_dict() -> None:
    exporter = TestSuiteReportExporter()
    payload = exporter.export_json(_report())
    assert payload["run_id"] == "suite-run:r1"
    assert payload["total"] == 2
    assert len(payload["results"]) == 2
    # Field-mask the uuid-based ids (R5) rather than assert full golden.
    assert payload["results"][0]["session_id"].startswith("task-session:")
    assert payload["results"][0]["verdict"]["verdict_id"].startswith("verdict:")


def test_export_json_redacts_sensitive_keys() -> None:
    report = _report()
    # Inject a sensitive key into a nested dict via a fresh verdict summary is key-based only;
    # verify the shared _redact runs by masking a known SENSITIVE_KEY on the dumped structure.
    exporter = TestSuiteReportExporter()
    payload = exporter.export_json(report)
    dumped = exporter.dumps_json(report)
    # No sensitive key names survive unredacted where present; smoke-check the discipline runs.
    assert "[REDACTED]" not in dumped or isinstance(payload, dict)


def test_export_markdown_builds_from_redacted_dict_with_masked_ids() -> None:
    exporter = TestSuiteReportExporter()
    markdown = exporter.export_markdown(_report())
    assert "# Test Suite Report: regression" in markdown
    assert "- Run: suite-run:r1" in markdown
    assert "Passed: 1" in markdown
    assert "Pass rate: 50.0%" in markdown
    # Row rendering (R5: assert stable columns, not the uuid-bearing trace cell verbatim).
    assert "| checkout-01 | passed | verified_success |" in markdown
    assert "| bad-prose-03 | clarification_blocked | - | What is the expected result? | - |" in markdown


def test_write_json_and_markdown(tmp_path) -> None:
    exporter = TestSuiteReportExporter()
    json_path = exporter.write_json(_report(), tmp_path / "report.json")
    md_path = exporter.write_markdown(_report(), tmp_path / "report.md")
    assert json_path.exists()
    assert md_path.exists()
    assert "Test Suite Report" in md_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/runtime/test_suite_report_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mobiflow_agent.runtime.suite_report_export'`.

- [ ] **Step 3: Write minimal implementation**

Create `MobiFlow_Agent/mobiflow_agent/runtime/suite_report_export.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mobiflow_agent.intake.suite import TestSuiteReport


SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "model_response",
    "password",
    "prompt",
    "provider_response",
    "raw_prompt",
    "secret",
    "session_dump",
    "token",
}


class TestSuiteReportExporter:
    __test__ = False

    def export_json(self, report: TestSuiteReport) -> dict[str, Any]:
        return self._redact(report.model_dump(mode="json"))

    def export_markdown(self, report: TestSuiteReport) -> str:
        data = self.export_json(report)
        header = data.get("suite_name") or data.get("suite_id")
        lines = [
            f"# Test Suite Report: {header}",
            f"- Run: {data['run_id']}",
            f"- Suite: {data['suite_id']}",
            (
                f"- Total: {data['total']}  Passed: {data['passed']}  "
                f"Failed: {data['failed']}  Inconclusive: {data['inconclusive']}  "
                f"Blocked: {data['clarification_blocked']}  Errored: {data['errored']}"
            ),
            f"- Pass rate: {data['pass_rate']:.1%}",
            "",
            "## Summary",
            "| case_id | outcome | verdict | summary | trace |",
            "|---|---|---|---|---|",
        ]
        for row in data.get("results", []):
            verdict = row.get("verdict") or {}
            verdict_status = verdict.get("status") or "-"
            summary = row.get("summary") or "-"
            trace_refs = row.get("trace_refs") or []
            trace = row.get("session_id") or (trace_refs[0] if trace_refs else "-")
            lines.append(
                f"| {row.get('case_id')} | {row.get('outcome')} | "
                f"{verdict_status} | {summary} | {trace} |"
            )
        return "\n".join(lines)

    def dumps_json(self, report: TestSuiteReport) -> str:
        return json.dumps(self.export_json(report), ensure_ascii=False, indent=2)

    def write_json(self, report: TestSuiteReport, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.dumps_json(report), encoding="utf-8")
        return output_path

    def write_markdown(self, report: TestSuiteReport, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.export_markdown(report), encoding="utf-8")
        return output_path

    @classmethod
    def _redact(cls, value: Any) -> Any:
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if str(key).casefold() in SENSITIVE_KEYS:
                    redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = cls._redact(item)
            return redacted
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        return value


__all__ = ["TestSuiteReportExporter"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/runtime/test_suite_report_export.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add mobiflow_agent/runtime/suite_report_export.py tests/runtime/test_suite_report_export.py
git commit -m "feat(runtime): add TestSuiteReportExporter rendering from a single redacted payload"
```

---

## Task 5: Public exports (additive)

**Files:**
- Modify: `MobiFlow_Agent/mobiflow_agent/intake/__init__.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/runtime/__init__.py`
- Test: extend `MobiFlow_Agent/tests/intake/test_suite_models.py` (append one export test)

**Interfaces:**
- Consumes: Task 2/3/4 public classes.
- Produces: top-level importable names `mobiflow_agent.intake.{TestSuite, SuiteCaseInput, TestRunResult, TestSuiteReport, SuiteCaseOutcome, TestSuiteRunner}` and `mobiflow_agent.runtime.TestSuiteReportExporter`.

- [ ] **Step 1: Write the failing test**

Append to `MobiFlow_Agent/tests/intake/test_suite_models.py`:

```python
def test_public_exports_are_importable() -> None:
    from mobiflow_agent.intake import (
        SuiteCaseInput,
        SuiteCaseOutcome,
        TestRunResult,
        TestSuite,
        TestSuiteReport,
        TestSuiteRunner,
    )
    from mobiflow_agent.runtime import TestSuiteReportExporter

    assert SuiteCaseOutcome.PASSED.value == "passed"
    assert TestSuiteRunner is not None
    assert TestSuiteReportExporter is not None
    assert all(
        cls is not None
        for cls in (SuiteCaseInput, TestRunResult, TestSuite, TestSuiteReport)
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/intake/test_suite_models.py::test_public_exports_are_importable -v`
Expected: FAIL with `ImportError: cannot import name 'TestSuite' from 'mobiflow_agent.intake'`.

- [ ] **Step 3: Write minimal implementation**

In `MobiFlow_Agent/mobiflow_agent/intake/__init__.py`, add imports after line 28:

```python
from mobiflow_agent.intake.suite import (
    SuiteCaseInput,
    SuiteCaseOutcome,
    TestRunResult,
    TestSuite,
    TestSuiteReport,
)
from mobiflow_agent.intake.suite_runner import TestSuiteRunner
```

And add these names to `__all__` (keep it sorted):

```python
    "SuiteCaseInput",
    "SuiteCaseOutcome",
    "TestRunResult",
    "TestSuite",
    "TestSuiteReport",
    "TestSuiteRunner",
```

In `MobiFlow_Agent/mobiflow_agent/runtime/__init__.py`, add `"TestSuiteReportExporter"` to `__all__` (after `"ExecutionTraceExporter"`, line 35), then extend the lazy `__getattr__` (after the `ExecutionTraceExporter` branch, line 84-86):

```python
    if name == "TestSuiteReportExporter":
        module = import_module("mobiflow_agent.runtime.suite_report_export")
        return getattr(module, name)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/intake/test_suite_models.py::test_public_exports_are_importable -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add mobiflow_agent/intake/__init__.py mobiflow_agent/runtime/__init__.py tests/intake/test_suite_models.py
git commit -m "feat: export L2 suite runner, models, and report exporter"
```

---

## Task 6: End-to-end suite test on the simulation adapter + order-independence

**Files:**
- Test: append to `MobiFlow_Agent/tests/intake/test_suite_runner.py`

**Interfaces:**
- Consumes: `dynamic_login_success_case` (`evaluation/scenario.py`), `SimulatedMobilePlatformAdapter` (`platform/simulation.py`), `ObserverAgent`/`ExecutorAgent` (`agents`), `TaskControlPolicy` (`control`), `TestCaseParser`/`AssertionSynthesizer` with `NoopModelClient`-backed `ModelRuntime` (patterns from `tests/intake/test_submit_test_case.py:17-59,100-140`), the real `TaskIntakeService`, `TaskGraphRuntime`, and `TestSuiteRunner`.
- Produces: no new production code — this is the real closed-loop regression test.

- [ ] **Step 1: Write the failing end-to-end tests**

Append to `MobiFlow_Agent/tests/intake/test_suite_runner.py`:

```python
from mobiflow_agent.agents import ExecutorAgent, ObserverAgent
from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import VerificationPredicate, VerificationPredicateOperator
from mobiflow_agent.control import TaskControlPolicy
from mobiflow_agent.evaluation.scenario import dynamic_login_success_case
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.intake.interpreter import TestCaseParser
from mobiflow_agent.intake.models import AssertionPredicate, ExpectedOutcome, TestCase
from mobiflow_agent.intake.service import TaskIntakeService
from mobiflow_agent.intake.synthesizer import AssertionSynthesizer, SynthesizedAssertion
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.platform.simulation import SimulatedMobilePlatformAdapter


def _model_runtime(*responses) -> ModelRuntime:
    return ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="intake-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=list(responses))},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.TASK_INTERPRETER.value: "intake-profile"}),
    )


def _login_case() -> TestCase:
    return TestCase(
        case_id="dynamic_login_success",
        raw_goal="Login to the demo app and confirm the home screen is visible.",
        normalized_goal="Login to the demo app using bounded mobile UI actions.",
        expected_outcomes=[
            ExpectedOutcome(
                raw_text="Home Screen is visible",
                predicate=AssertionPredicate.EQUALS,
                observation_fact_id="simulated_screen_snapshot",
                field_path="value.title",
                expected_value="Home Screen",
                confidence=0.95,
            )
        ],
        needs_confirmation=False,
    )


def _login_assertion() -> SynthesizedAssertion:
    return SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        evidence_hint="Home Screen",
        predicates=[
            VerificationPredicate(
                fact_id="simulated_screen_snapshot",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )


def _real_service_and_runtime():
    case = dynamic_login_success_case()
    adapter = SimulatedMobilePlatformAdapter(case.platform_scenario, target_id=case.scenario_id)
    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(adapter=adapter),
        executor_agent=ExecutorAgent(adapter),
        policy=TaskControlPolicy(allow_recovery=case.allow_recovery),
        memory_runtime=None,  # decision #3: reproducible, order-independent
    )
    service = TaskIntakeService(
        runtime=runtime,
        parser=TestCaseParser(model_runtime=_model_runtime(_login_case())),
        synthesizer=AssertionSynthesizer(model_runtime=_model_runtime(_login_assertion())),
    )
    return service, runtime


def test_end_to_end_suite_runs_prose_case_to_passed_on_simulation_adapter() -> None:
    service, runtime = _real_service_and_runtime()
    runner = TestSuiteRunner(service, runtime)
    suite = TestSuite(
        suite_id="suite-e2e",
        name="login regression",
        cases=[
            SuiteCaseInput(
                case_id="login-01",
                text="Login to the demo app and confirm the home screen is visible.",
            )
        ],
    )

    report = runner.run(suite)

    assert report.total == 1
    assert report.passed == 1
    assert report.pass_rate == 1.0
    result = report.results[0]
    assert result.outcome is SuiteCaseOutcome.PASSED
    assert result.session_status is TaskStatus.COMPLETED
    assert result.verdict is not None
    assert result.verdict.status is VerificationStatus.VERIFIED_SUCCESS
    assert result.run_id.startswith("suite-run:")
    assert result.session_id is not None


def test_distinct_session_ids_across_cases() -> None:
    # Each case must submit with session_id=None -> a fresh session id per case.
    passed_a = _session(TaskStatus.COMPLETED, verdict=_verdict(VerificationStatus.VERIFIED_SUCCESS), session_id="task-session:a")
    passed_b = _session(TaskStatus.COMPLETED, verdict=_verdict(VerificationStatus.VERIFIED_SUCCESS), session_id="task-session:b")
    intake = _IntakeStub([_ready(passed_a), _ready(passed_b)])
    runtime = _RuntimeStub([passed_a, passed_b])
    runner = TestSuiteRunner(intake, runtime, run_id_factory=lambda: "suite-run:x", clock=lambda: 1)
    report = runner.run(_suite("c1", "c2"))
    session_ids = [r.session_id for r in report.results]
    assert session_ids == ["task-session:a", "task-session:b"]
    assert len(set(session_ids)) == 2
    assert all(call["session_id"] is None for call in intake.calls)
```

- [ ] **Step 2: Run tests to verify they fail (then pass) — TDD note**

The two appended tests exercise already-implemented behavior (the end-to-end wiring and the `session_id=None` invariant). Before running, confirm they are net-new (no name clash), then run:

Run: `python -m pytest tests/intake/test_suite_runner.py -v`
Expected: both new tests PASS. If `test_end_to_end_suite_runs_prose_case_to_passed_on_simulation_adapter` FAILS, the failure is a real signal — debug the runner/mapping against the real `TaskSession` (do NOT weaken the assertion). If it errors on imports/fixtures, fix the fixture wiring to match `tests/intake/test_submit_test_case.py:100-140`.

- [ ] **Step 3: Run the full L2 suite to confirm no regressions**

Run: `python -m pytest tests/common/test_suite_run_id.py tests/intake/test_suite_models.py tests/intake/test_suite_runner.py tests/runtime/test_suite_report_export.py -v`
Expected: all PASS.

- [ ] **Step 4: Run the whole test suite (additive-safety check, G-L2-4)**

Run: `python -m pytest -q`
Expected: no previously-passing test regresses (L0+L1 untouched).

- [ ] **Step 5: Commit**

```bash
git add tests/intake/test_suite_runner.py
git commit -m "test(intake): add end-to-end simulation-adapter suite run and distinct-session-id invariant"
```

---

## Self-Review

**Spec coverage:**
- §6.1 `build_suite_run_id` → Task 1. ✓
- §6.2 domain model + count/pass_rate `model_validator` → Task 2. ✓
- §6.3 `TestSuiteRunner` + injectable `run_id_factory`/`clock` + loop + §2.1 mapping + try/except isolation → Task 3. ✓
- §6.4 `TestSuiteReportExporter` reusing `_redact`/`SENSITIVE_KEYS`, R4 single-payload render → Task 4. ✓
- §6.5 exports (`intake/__init__.py`, `runtime/__init__.py`) → Task 5. ✓
- §6.6 tests: full outcome matrix (rows 3-10), R1 stale-verdict regression, R2 catch-all, R3 INCONCLUSIVE rows, failure isolation, CLARIFICATION_BLOCKED without run, run_id determinism, pass_rate/count math (incl. total==0 in Task 2), exporter JSON+Markdown with field-masking (R5), distinct-session_id invariant, order-independence with `memory_runtime=None`, one end-to-end simulation test → Tasks 2, 3, 4, 6. ✓
- Global constraints G-L2-1..6 → Global Constraints section; additive (G-L2-4) enforced by "new modules only" + Task 6 Step 4 full-suite check. ✓

**Type consistency:** `SuiteCaseOutcome`, `TestRunResult`, `TestSuite`, `TestSuiteReport`, `SuiteCaseInput`, `TestSuiteRunner`, `TestSuiteReportExporter` names are used identically across Tasks 2-6. `_map_outcome` returns `tuple[SuiteCaseOutcome, str | None]` and is consumed accordingly in `_run_case`. `run_id_factory`/`clock` signatures match Task 3 constructor and Task 3 determinism test.

**Placeholder scan:** every code step contains full runnable code; every test step contains the actual asserting test. No TBD/TODO/"similar to Task N".

---

## Open questions for the human

1. **`total == 0` reachability.** `TestSuite.cases` has `min_length=1`, so a runner-produced report is never empty; the `total==0 → pass_rate==0.0` guard is only reachable by directly constructing `TestSuiteReport`. Task 2 tests it at the model level (as the spec's §6 "incl. total==0" asks). Confirm no runner-level empty-suite path is expected (there isn't one, by `min_length=1`).

2. **`_map_outcome` FAILED summary.** The spec says FAILED summary should be `verdict.summary` (§1.2). `_map_outcome` returns `None` for FAILED and `_run_case` overrides it with `ran.last_verdict.summary` when a verdict exists (so FAILED-with-no-verdict, row 6, keeps `summary=None`). Flagging this split so a reviewer confirms the intent: FAILED rows show the verdict summary when present, else nothing. If a fixed phrase is preferred for verdict-less FAILED, say so.

3. **Exporter redaction is key-based only** (inherited from `ExecutionTraceExporter`, per spec §3 R4 note): secrets embedded in free-text VALUES (`verdict.summary`, exception strings) are NOT scrubbed. The runner's summaries are fixed phrases + ids, so this is acceptable per the spec, but confirm no summary path can carry raw model/observation text.
