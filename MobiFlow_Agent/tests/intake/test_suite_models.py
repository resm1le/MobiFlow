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
