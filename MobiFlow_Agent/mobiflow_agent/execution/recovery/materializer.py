from __future__ import annotations

"""Recovery proposal materialization types and logic."""

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import Field

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, StrictModel
from mobiflow_agent.platform.types import (
    AttemptContext,
    FailureTriageRecord,
    RecoveryGuidance,
    RunGovernanceSnapshot,
    RunLineageSnapshot,
    RunTargetContext,
    ToolCatalogItem,
)

class RecoveryMaterializationStatus(str, Enum):
    READY = "ready"
    REQUIRES_INPUT = "requires_input"
    BLOCKED = "blocked"
    OBSERVE_ONLY = "observe_only"

class RunRecoverySeed(StrictModel):
    run_id: str = Field(min_length=1)
    run_target_id: str = Field(min_length=1)
    source_run_status: str = Field(min_length=1)
    name: str | None = None
    description: str | None = None
    device_pool_id: str | None = None
    device_id: str | None = None
    task_type: str | None = None
    profile_package: str | None = None
    task_payload: dict[str, Any] = Field(default_factory=dict)
    run_config: dict[str, Any] = Field(default_factory=dict)
    artifact_policy: dict[str, Any] = Field(default_factory=dict)
    priority: int | None = None
    labels: list[str] = Field(default_factory=list)
    source: str | None = None
    created_by: str | None = None
    max_retries_per_device: int | None = None
    queue_timeout_ms: int | None = None

class MaterializedRecoveryAction(StrictModel):
    action_name: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool
    missing_inputs: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None

class RecoveryMaterializationResult(StrictModel):
    status: RecoveryMaterializationStatus
    materialized_action: MaterializedRecoveryAction | None = None
    proposal: ExecutionProposal | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None

class RecoveryProposalMaterializer:
    def materialize(
        self,
        *,
        triage: FailureTriageRecord,
        guidance: RecoveryGuidance,
        run_target: RunTargetContext,
        attempt: AttemptContext | None,
        governance_snapshot: RunGovernanceSnapshot,
        lineage_snapshot: RunLineageSnapshot,
        catalog: list[ToolCatalogItem],
    ) -> RecoveryMaterializationResult:
        action_name = guidance.recommended_action
        if action_name == "continue_observe":
            action = MaterializedRecoveryAction(
                action_name=action_name,
                tool_name=action_name,
                arguments={},
                requires_approval=False,
                blocked_reason="continue_observe",
            )
            return RecoveryMaterializationResult(
                status=RecoveryMaterializationStatus.OBSERVE_ONLY,
                materialized_action=action,
                blocked_reason=action.blocked_reason,
            )

        if action_name not in guidance.allowed_actions:
            action = MaterializedRecoveryAction(
                action_name=action_name,
                tool_name=action_name,
                arguments={},
                requires_approval=guidance.requires_approval,
                blocked_reason="recommended_action_not_allowed",
            )
            return RecoveryMaterializationResult(
                status=RecoveryMaterializationStatus.BLOCKED,
                materialized_action=action,
                blocked_reason=action.blocked_reason,
            )

        if action_name == "cancel_run":
            tool = self._tool_by_name(catalog, "cancel_run")
            requires_approval = tool.requires_approval if tool is not None else guidance.requires_approval
            action = MaterializedRecoveryAction(
                action_name=action_name,
                tool_name="cancel_run",
                arguments={"runId": guidance.entity_id},
                requires_approval=requires_approval,
            )
            proposal = self._build_proposal(
                triage=triage,
                guidance=guidance,
                run_target=run_target,
                governance_snapshot=governance_snapshot,
                action=action,
            )
            return RecoveryMaterializationResult(
                status=RecoveryMaterializationStatus.READY,
                materialized_action=action,
                proposal=proposal,
            )

        if action_name not in {"create_run", "create_single_device_run"}:
            action = MaterializedRecoveryAction(
                action_name=action_name,
                tool_name=action_name,
                arguments={},
                requires_approval=guidance.requires_approval,
                blocked_reason="unsupported_recommended_action",
            )
            return RecoveryMaterializationResult(
                status=RecoveryMaterializationStatus.BLOCKED,
                materialized_action=action,
                blocked_reason=action.blocked_reason,
            )

        tool = self._tool_by_name(catalog, action_name)
        if tool is None:
            action = MaterializedRecoveryAction(
                action_name=action_name,
                tool_name=action_name,
                arguments={},
                requires_approval=guidance.requires_approval,
                blocked_reason="tool_catalog_missing",
            )
            return RecoveryMaterializationResult(
                status=RecoveryMaterializationStatus.BLOCKED,
                materialized_action=action,
                blocked_reason=action.blocked_reason,
            )

        seed = self._build_seed(
            run_target=run_target,
            attempt=attempt,
            governance_snapshot=governance_snapshot,
            lineage_snapshot=lineage_snapshot,
        )
        arguments = self._seed_to_arguments(action_name, seed)
        required_fields = self._required_fields(tool)
        missing_inputs = sorted(
            field_name
            for field_name in required_fields
            if field_name not in arguments or self._is_missing(arguments[field_name])
        )
        if missing_inputs:
            action = MaterializedRecoveryAction(
                action_name=action_name,
                tool_name=action_name,
                arguments=arguments,
                requires_approval=tool.requires_approval,
                missing_inputs=missing_inputs,
                blocked_reason="missing_materialization_inputs",
            )
            return RecoveryMaterializationResult(
                status=RecoveryMaterializationStatus.REQUIRES_INPUT,
                materialized_action=action,
                missing_inputs=missing_inputs,
                blocked_reason=action.blocked_reason,
            )

        action = MaterializedRecoveryAction(
            action_name=action_name,
            tool_name=action_name,
            arguments=arguments,
            requires_approval=tool.requires_approval,
        )
        proposal = self._build_proposal(
            triage=triage,
            guidance=guidance,
            run_target=run_target,
            governance_snapshot=governance_snapshot,
            action=action,
        )
        return RecoveryMaterializationResult(
            status=RecoveryMaterializationStatus.READY,
            materialized_action=action,
            proposal=proposal,
        )

    @staticmethod
    def _tool_by_name(catalog: list[ToolCatalogItem], tool_name: str) -> ToolCatalogItem | None:
        for item in catalog:
            if item.name == tool_name:
                return item
        return None

    @staticmethod
    def _required_fields(tool: ToolCatalogItem) -> list[str]:
        required = tool.input_schema.get("required")
        return [field for field in required if isinstance(field, str)] if isinstance(required, list) else []

    def _build_seed(
        self,
        *,
        run_target: RunTargetContext,
        attempt: AttemptContext | None,
        governance_snapshot: RunGovernanceSnapshot,
        lineage_snapshot: RunLineageSnapshot,
    ) -> RunRecoverySeed:
        run_detail = lineage_snapshot.run
        lineage_target = next(
            (target for target in lineage_snapshot.targets if target.run_target_id == run_target.run_target_id),
            None,
        )
        device_id = self._resolve_device_id(run_target, attempt, lineage_target)
        return RunRecoverySeed(
            run_id=governance_snapshot.run_id,
            run_target_id=run_target.run_target_id,
            source_run_status=governance_snapshot.status,
            name=run_detail.run.name,
            description=run_detail.run.description,
            device_pool_id=run_detail.run.pool_id,
            device_id=device_id,
            task_type=run_detail.run.task_type,
            profile_package=run_detail.run.profile_package,
            task_payload=run_detail.task_payload,
            run_config=run_detail.run_config,
            artifact_policy=run_detail.artifact_policy,
            priority=run_detail.run.priority,
            labels=run_detail.run.labels,
            source=run_detail.run.source,
            created_by=run_detail.run.created_by,
            max_retries_per_device=run_detail.run.max_retries_per_device,
            queue_timeout_ms=run_detail.run.queue_timeout_ms,
        )

    @staticmethod
    def _resolve_device_id(
        run_target: RunTargetContext,
        attempt: AttemptContext | None,
        lineage_target: RunTargetContext | None,
    ) -> str | None:
        if run_target.device_id:
            return run_target.device_id
        if run_target.latest_attempt is not None and run_target.latest_attempt.device_id:
            return run_target.latest_attempt.device_id
        if attempt is not None and attempt.device_id:
            return attempt.device_id
        if lineage_target is not None and lineage_target.device_id:
            return lineage_target.device_id
        return None

    @staticmethod
    def _seed_to_arguments(action_name: str, seed: RunRecoverySeed) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "name": seed.name,
            "description": seed.description,
            "taskType": seed.task_type,
            "profilePackage": seed.profile_package,
            "taskPayload": seed.task_payload,
            "runConfig": seed.run_config,
            "artifactPolicy": seed.artifact_policy,
            "priority": seed.priority,
            "labels": seed.labels,
            "source": seed.source,
            "createdBy": seed.created_by,
            "maxRetriesPerDevice": seed.max_retries_per_device,
            "queueTimeoutMs": seed.queue_timeout_ms,
        }
        if action_name == "create_run":
            arguments["devicePoolId"] = seed.device_pool_id
        elif action_name == "create_single_device_run":
            arguments["deviceId"] = seed.device_id

        return {
            key: value
            for key, value in arguments.items()
            if value is not None and (not isinstance(value, str) or value.strip())
        }

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    def _build_proposal(
        self,
        *,
        triage: FailureTriageRecord,
        guidance: RecoveryGuidance,
        run_target: RunTargetContext,
        governance_snapshot: RunGovernanceSnapshot,
        action: MaterializedRecoveryAction,
    ) -> ExecutionProposal:
        return ExecutionProposal(
            proposal_id=f"proposal:{uuid4().hex}",
            action_tool_name=action.tool_name,
            arguments=action.arguments,
            target_kind=EntityKind.RUN_TARGET,
            target_id=run_target.run_target_id,
            rationale=(
                f"Platform guidance recommends {action.action_name} for run target {run_target.run_target_id} "
                f"after {triage.failure_category.value}: {triage.probable_cause}"
            ),
            preconditions=self._build_preconditions(
                action=action,
                guidance=guidance,
                run_target=run_target,
                governance_snapshot=governance_snapshot,
            ),
            expected_observation_changes=self._expected_changes(action.action_name, guidance.entity_id),
            confidence=guidance.confidence,
        )

    @staticmethod
    def _build_preconditions(
        *,
        action: MaterializedRecoveryAction,
        guidance: RecoveryGuidance,
        run_target: RunTargetContext,
        governance_snapshot: RunGovernanceSnapshot,
    ) -> dict[str, Any]:
        if action.action_name == "cancel_run":
            return {"runId": guidance.entity_id, "status": governance_snapshot.status}
        if action.action_name == "create_single_device_run":
            return {
                "runId": guidance.entity_id,
                "sourceRunTargetId": run_target.run_target_id,
                "deviceId": action.arguments.get("deviceId"),
            }
        return {
            "runId": guidance.entity_id,
            "sourceRunTargetId": run_target.run_target_id,
        }

    @staticmethod
    def _expected_changes(action_name: str, run_id: str) -> list[str]:
        if action_name == "cancel_run":
            return [f"run {run_id} transitions away from the blocked state via cancellation"]
        if action_name == "create_single_device_run":
            return [f"a replacement single-device run is created for run {run_id}"]
        if action_name == "create_run":
            return [f"a replacement pooled run is created for run {run_id}"]
        return []
