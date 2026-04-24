from __future__ import annotations

"""Recovery outcome follow-up contracts and service."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, StrictModel, VerificationStatus, VerificationVerdict
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.platform.types import RunGovernanceSnapshot, RunLineageSnapshot, RunTargetContext

QUEUE_LIKE_RUN_STATUSES = {"QUEUED", "PENDING", "CREATED", "SCHEDULED", "READY"}
FAILED_OR_BLOCKED_TARGET_STATUSES = {"FAILED", "BLOCKED", "CANCELLED"}

class RecoveryFollowupStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"

class RecoveryOutcomeFollowupContext(StrictModel):
    run_target_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    created_run_id: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    expected_device_id: str | None = None

class RecoveryOutcomeObservation(StrictModel):
    created_governance: RunGovernanceSnapshot | None = None
    created_lineage: RunLineageSnapshot | None = None
    candidate_next_run_target_id: str | None = None

class RecoveryOutcomeFollowupResponse(StrictModel):
    status: RecoveryFollowupStatus
    context: RecoveryOutcomeFollowupContext
    verdict: VerificationVerdict | None = None
    next_recovery_run_target_id: str | None = None
    summary: str = Field(min_length=1)

class RecoveryOutcomeFollowupService:
    def __init__(self, adapter: PlatformAdapter):
        self._adapter = adapter

    def assess(self, run_target_id: str, created_run_id: str) -> RecoveryOutcomeFollowupResponse:
        if not created_run_id.strip():
            raise ValueError("created_run_id is required.")

        run_target = self._adapter.get_run_target(run_target_id)
        source_run_id = self._resolve_source_run_id(run_target)
        created_governance = self._adapter.get_run_governance_snapshot(created_run_id)
        created_lineage = self._adapter.get_run_lineage_snapshot(created_run_id)
        action_name = self._infer_action_name(run_target, created_lineage)
        context = RecoveryOutcomeFollowupContext(
            run_target_id=run_target_id,
            source_run_id=source_run_id,
            created_run_id=created_run_id,
            action_name=action_name,
            expected_device_id=run_target.device_id,
        )
        candidate_next_run_target_id = self._candidate_next_run_target_id(created_lineage)
        observation = RecoveryOutcomeObservation(
            created_governance=created_governance,
            created_lineage=created_lineage,
            candidate_next_run_target_id=candidate_next_run_target_id,
        )
        if action_name == "create_single_device_run":
            return self._assess_single_device(context, observation)
        return self._assess_create_run(context, observation)

    def _assess_create_run(
        self,
        context: RecoveryOutcomeFollowupContext,
        observation: RecoveryOutcomeObservation,
    ) -> RecoveryOutcomeFollowupResponse:
        governance = observation.created_governance
        assert governance is not None

        if self._is_followup_success(governance):
            verdict = VerificationVerdict(
                verdict_id=f"verdict:followup:{context.created_run_id}:success",
                status=VerificationStatus.VERIFIED_SUCCESS,
                summary=(
                    f"Created run {context.created_run_id} has started producing execution evidence "
                    f"for recovery follow-up."
                ),
                target_kind=EntityKind.RUN_TARGET,
                target_id=context.run_target_id,
                matched_check_ids=["created_run_progressed"],
                evidence_refs=self._followup_evidence(context.created_run_id, include_lineage=False),
            )
            return self._completed_response(
                context=context,
                verdict=verdict,
                next_recovery_run_target_id=None,
            )

        if governance.status == "BLOCKED" or governance.blockers:
            verdict = VerificationVerdict(
                verdict_id=f"verdict:followup:{context.created_run_id}:blocked",
                status=VerificationStatus.BLOCKED,
                summary=f"Created run {context.created_run_id} is blocked during recovery follow-up.",
                target_kind=EntityKind.RUN_TARGET,
                target_id=context.run_target_id,
                blocked_reason="created_run_blocked",
                evidence_refs=self._followup_evidence(context.created_run_id, include_lineage=True),
            )
            return self._completed_response(
                context=context,
                verdict=verdict,
                next_recovery_run_target_id=observation.candidate_next_run_target_id,
            )

        if self._is_followup_failed(governance):
            verdict = VerificationVerdict(
                verdict_id=f"verdict:followup:{context.created_run_id}:failed",
                status=VerificationStatus.VERIFIED_FAILED,
                summary=f"Created run {context.created_run_id} entered a terminal failure state during follow-up.",
                target_kind=EntityKind.RUN_TARGET,
                target_id=context.run_target_id,
                unmatched_check_ids=["created_run_progressed"],
                evidence_refs=self._followup_evidence(context.created_run_id, include_lineage=True),
            )
            return self._completed_response(
                context=context,
                verdict=verdict,
                next_recovery_run_target_id=observation.candidate_next_run_target_id,
            )

        if self._is_pending(governance):
            return RecoveryOutcomeFollowupResponse(
                status=RecoveryFollowupStatus.PENDING,
                context=context,
                verdict=None,
                next_recovery_run_target_id=None,
                summary=(
                    f"Created run {context.created_run_id} is readable but has not yet produced enough execution "
                    f"evidence to conclude the recovery outcome."
                ),
            )

        verdict = VerificationVerdict(
            verdict_id=f"verdict:followup:{context.created_run_id}:unknown",
            status=VerificationStatus.VERIFIED_UNKNOWN,
            summary=(
                f"Created run {context.created_run_id} is readable, but the available governance and lineage "
                f"signals are not sufficient to conclude the follow-up outcome."
            ),
            target_kind=EntityKind.RUN_TARGET,
            target_id=context.run_target_id,
            evidence_refs=self._followup_evidence(context.created_run_id, include_lineage=True),
        )
        return self._completed_response(
            context=context,
            verdict=verdict,
            next_recovery_run_target_id=None,
        )

    def _assess_single_device(
        self,
        context: RecoveryOutcomeFollowupContext,
        observation: RecoveryOutcomeObservation,
    ) -> RecoveryOutcomeFollowupResponse:
        base = self._assess_create_run(context, observation)
        if base.status == RecoveryFollowupStatus.PENDING or base.verdict is None:
            return base
        if base.verdict.status != VerificationStatus.VERIFIED_SUCCESS:
            return base

        lineage = observation.created_lineage
        if lineage is None or not lineage.targets:
            return self._completed_response(
                context=context,
                verdict=VerificationVerdict(
                    verdict_id=f"verdict:followup:{context.created_run_id}:device-unknown",
                    status=VerificationStatus.VERIFIED_UNKNOWN,
                    summary=(
                        f"Created run {context.created_run_id} progressed, but device binding could not be "
                        f"proven for follow-up."
                    ),
                    target_kind=EntityKind.RUN_TARGET,
                    target_id=context.run_target_id,
                    evidence_refs=self._followup_evidence(context.created_run_id, include_lineage=True),
                ),
                next_recovery_run_target_id=None,
            )

        expected_device_id = context.expected_device_id
        if expected_device_id and any(target.device_id == expected_device_id for target in lineage.targets):
            verdict = VerificationVerdict(
                verdict_id=f"verdict:followup:{context.created_run_id}:device-success",
                status=VerificationStatus.VERIFIED_SUCCESS,
                summary=(
                    f"Created run {context.created_run_id} progressed and preserved the expected device binding "
                    f"for {expected_device_id}."
                ),
                target_kind=EntityKind.RUN_TARGET,
                target_id=context.run_target_id,
                matched_check_ids=["created_run_progressed", "expected_device_binding"],
                evidence_refs=self._followup_evidence(context.created_run_id, include_lineage=True),
            )
            return self._completed_response(
                context=context,
                verdict=verdict,
                next_recovery_run_target_id=None,
            )

        if expected_device_id and all(target.device_id != expected_device_id for target in lineage.targets):
            verdict = VerificationVerdict(
                verdict_id=f"verdict:followup:{context.created_run_id}:device-failed",
                status=VerificationStatus.VERIFIED_FAILED,
                summary=(
                    f"Created run {context.created_run_id} progressed, but its targets do not preserve the "
                    f"expected device binding for {expected_device_id}."
                ),
                target_kind=EntityKind.RUN_TARGET,
                target_id=context.run_target_id,
                unmatched_check_ids=["expected_device_binding"],
                evidence_refs=self._followup_evidence(context.created_run_id, include_lineage=True),
            )
            return self._completed_response(
                context=context,
                verdict=verdict,
                next_recovery_run_target_id=observation.candidate_next_run_target_id,
            )

        verdict = VerificationVerdict(
            verdict_id=f"verdict:followup:{context.created_run_id}:device-unknown",
            status=VerificationStatus.VERIFIED_UNKNOWN,
            summary=(
                f"Created run {context.created_run_id} progressed, but the expected device binding could not be "
                f"conclusively verified."
            ),
            target_kind=EntityKind.RUN_TARGET,
            target_id=context.run_target_id,
            evidence_refs=self._followup_evidence(context.created_run_id, include_lineage=True),
        )
        return self._completed_response(
            context=context,
            verdict=verdict,
            next_recovery_run_target_id=None,
        )

    def _resolve_source_run_id(self, run_target: RunTargetContext) -> str:
        if run_target.latest_attempt is not None and run_target.latest_attempt.run_id:
            return run_target.latest_attempt.run_id
        if run_target.latest_attempt_id:
            attempt = self._adapter.get_attempt(run_target.latest_attempt_id)
            return attempt.run_id
        raise ValueError(f"Could not resolve source_run_id for run target {run_target.run_target_id}.")

    @staticmethod
    def _infer_action_name(run_target: RunTargetContext, created_lineage: RunLineageSnapshot) -> str:
        if created_lineage.run.run.pool_id is None and run_target.device_id:
            return "create_single_device_run"
        return "create_run"

    @staticmethod
    def _is_followup_success(governance: RunGovernanceSnapshot) -> bool:
        return (
            governance.attempt_counts.total > 0
            or governance.target_counts.running + governance.target_counts.succeeded > 0
        )

    @staticmethod
    def _is_followup_failed(governance: RunGovernanceSnapshot) -> bool:
        if governance.status in {"FAILED", "CANCELLED"}:
            return True
        failed_or_cancelled = governance.target_counts.failed + governance.target_counts.cancelled
        progressed = governance.target_counts.running + governance.target_counts.succeeded
        return failed_or_cancelled > 0 and progressed == 0

    @staticmethod
    def _is_pending(governance: RunGovernanceSnapshot) -> bool:
        has_progress = governance.attempt_counts.total > 0 or (
            governance.target_counts.running + governance.target_counts.succeeded > 0
        )
        has_terminal = governance.target_counts.failed + governance.target_counts.cancelled > 0
        return governance.status in QUEUE_LIKE_RUN_STATUSES and not has_progress and not has_terminal and not governance.blockers

    @staticmethod
    def _candidate_next_run_target_id(created_lineage: RunLineageSnapshot) -> str | None:
        candidates = [
            target.run_target_id
            for target in created_lineage.targets
            if target.status in FAILED_OR_BLOCKED_TARGET_STATUSES
        ]
        if len(candidates) == 1:
            return candidates[0]
        return None

    @staticmethod
    def _followup_evidence(created_run_id: str, *, include_lineage: bool) -> list[EvidenceRef]:
        evidence = [
            EvidenceRef(
                evidence_id=f"snapshot:get_run_governance_snapshot:run:{created_run_id}",
                kind=EvidenceKind.PLATFORM_SNAPSHOT,
                summary=f"get_run_governance_snapshot for run {created_run_id}.",
                locator=created_run_id,
            )
        ]
        if include_lineage:
            evidence.append(
                EvidenceRef(
                    evidence_id=f"snapshot:get_run_lineage_snapshot:run:{created_run_id}",
                    kind=EvidenceKind.PLATFORM_SNAPSHOT,
                    summary=f"get_run_lineage_snapshot for run {created_run_id}.",
                    locator=created_run_id,
                )
            )
        return evidence

    @staticmethod
    def _completed_response(
        *,
        context: RecoveryOutcomeFollowupContext,
        verdict: VerificationVerdict,
        next_recovery_run_target_id: str | None,
    ) -> RecoveryOutcomeFollowupResponse:
        return RecoveryOutcomeFollowupResponse(
            status=RecoveryFollowupStatus.COMPLETED,
            context=context,
            verdict=verdict,
            next_recovery_run_target_id=next_recovery_run_target_id,
            summary=verdict.summary,
        )
