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
