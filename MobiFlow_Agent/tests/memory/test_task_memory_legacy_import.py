from __future__ import annotations

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.evaluation.replay import RecoveryReplayCase
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from mobiflow_agent.execution.recovery.models import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory import InMemoryTaskMemoryStore, TaskMemoryLegacyImportService, TaskMemoryRecordKind
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle
from tests.harness_helpers import build_task_harness_response


def test_legacy_recovery_memory_imports_as_task_memory_record() -> None:
    verdict = VerificationVerdict(
        verdict_id="verdict:legacy",
        status=VerificationStatus.VERIFIED_SUCCESS,
        summary="Legacy recovery completed with evidence.",
        target_kind=EntityKind.RUN_TARGET,
        target_id="rt-1",
        evidence_refs=[
            EvidenceRef(
                evidence_id="evidence:legacy",
                kind=EvidenceKind.PLATFORM_SNAPSHOT,
                summary="Legacy evidence.",
                locator="rt-1",
            )
        ],
    )
    replay_case = RecoveryReplayCase(
        case_id="replay:legacy",
        source="legacy-test",
        execution=GovernedRecoveryExecutionResponse(
            thread_id="thread-1",
            run_target_id="rt-1",
            run_id="run-1",
            action_name="cancel_run",
            created_run_id=None,
            followup_required=False,
            lifecycle=RuntimeLifecycle.COMPLETED,
            verdict=verdict,
            approval_request=None,
            runtime_state=AgentRuntimeState(
                session_id="session-1",
                lifecycle=RuntimeLifecycle.COMPLETED,
                latest_verdict=verdict,
            ),
        ),
        harness_response=build_task_harness_response(
            decision=RecoveryFollowupDriverDecision.COMPLETE,
            verdict=verdict,
        ),
    )
    memory_case = MemoryCaseRetrievalService().build_case(
        source="legacy-catalog",
        replay_case=replay_case,
        category="blocked-run",
        input_summary="Cancel run recovered a blocked target.",
        tags=["recovery", "blocked"],
    )
    store = InMemoryTaskMemoryStore()

    result = TaskMemoryLegacyImportService(store=store).import_cases([memory_case])

    assert result.created_count == 1
    assert result.rejected_count == 0
    assert store.list_records()[0].kind == TaskMemoryRecordKind.RECOVERY_PATTERN
