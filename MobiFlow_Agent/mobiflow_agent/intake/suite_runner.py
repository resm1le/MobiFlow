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
