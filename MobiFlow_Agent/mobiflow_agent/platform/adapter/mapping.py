from __future__ import annotations

from typing import Any

from mobiflow_agent.platform.adapter.protocol import PlatformAdapterError
from mobiflow_agent.platform.types import (
    AuditTimelineEntry,
    AvailableDevicePoolContext,
    AvailableProfileContext,
    AttemptArtifactResource,
    AttemptContext,
    FailureCategory,
    FailureTriageRecord,
    FailureTriageValidation,
    DispatchDeviceContext,
    GovernedActionResult,
    GovernedActionState,
    PlatformEntityRefs,
    PlatformArtifactPolicy,
    PlatformRunConfig,
    RecoveryGuidance,
    RetryRecommendation,
    RunAttemptCounts,
    RunCounts,
    RunDetailContext,
    RunGovernanceSnapshot,
    RunLineageSnapshot,
    RunPlanningCatalogContext,
    RunPlanningDefaultPolicy,
    RunSummaryContext,
    RunTargetContext,
    SuggestedNextAction,
    ToolAuditRef,
    ToolCatalogItem,
    ToolExecutionError,
    ToolRiskLevel,
)
from mobiflow_agent.runtime.state import CallerContext


def require_completed_tool_payload(tool: str, response: dict[str, Any]) -> Any:
    status = response.get("status")
    if status == "completed":
        result = response.get("result")
        return {} if result is None else result
    error_payload = response.get("error") or {}
    code = error_payload.get("code", f"{tool.upper()}_FAILED")
    message = error_payload.get("message", f"{tool} did not complete successfully.")
    retryable = bool(error_payload.get("retryable", False))
    raise PlatformAdapterError(code, message, retryable=retryable)


def require_completed_tool_result(tool: str, response: dict[str, Any]) -> dict[str, Any]:
    result = require_completed_tool_payload(tool, response)
    if not isinstance(result, dict):
        raise PlatformAdapterError(
            "INVALID_PLATFORM_CONTRACT",
            f"{tool} returned a non-object result.",
            retryable=False,
        )
    return result


def map_dispatch_device_context(device: dict[str, Any]) -> DispatchDeviceContext:
    return DispatchDeviceContext(
        device_id=device["deviceId"],
        installed_profiles=list(device["installedProfiles"]),
        tags=list(device["tags"]),
        host_group=device.get("hostGroup"),
        registered=device["registered"],
        online=device["online"],
        busy=device["busy"],
        status=device["status"],
        updated_at=device["updatedAt"],
    )


def map_run_planning_catalog_context(catalog: dict[str, Any]) -> RunPlanningCatalogContext:
    policy = catalog["defaultRunPolicy"]
    run_config = policy["defaultRunConfig"]
    artifact_policy = policy["defaultArtifactPolicy"]
    return RunPlanningCatalogContext(
        available_device_pools=[
            AvailableDevicePoolContext(
                pool_id=pool["poolId"],
                name=pool["name"],
                host_group=pool.get("hostGroup"),
                device_count=pool["deviceCount"],
                required_tags=list(pool.get("requiredTags") or []),
                excluded_tags=list(pool.get("excludedTags") or []),
            )
            for pool in catalog["availableDevicePools"]
        ],
        available_profiles=[
            AvailableProfileContext(
                profile_package=profile["profilePackage"],
                installed_device_count=profile["installedDeviceCount"],
                supported_task_types=list(profile.get("supportedTaskTypes") or []),
                required_task_payload_fields=list(profile.get("requiredTaskPayloadFields") or []),
                recommended_defaults=dict(profile.get("recommendedDefaults") or {}),
                known_limitations=list(profile.get("knownLimitations") or []),
            )
            for profile in catalog["availableProfiles"]
        ],
        default_run_policy=RunPlanningDefaultPolicy(
            priority=policy["priority"],
            max_retries_per_device=policy["maxRetriesPerDevice"],
            queue_timeout_ms=policy["queueTimeoutMs"],
            default_run_config=PlatformRunConfig(
                loop_count=run_config["loopCount"],
                budget_ms=run_config["budgetMs"],
                loop_interval_ms=run_config["loopIntervalMs"],
                network_isolation_enabled=run_config["networkIsolationEnabled"],
                poll_interval_ms=run_config["pollIntervalMs"],
                heartbeat_interval_ms=run_config["heartbeatIntervalMs"],
            ),
            default_artifact_policy=PlatformArtifactPolicy(
                upload_log=artifact_policy["uploadLog"],
                upload_screenshot=artifact_policy["uploadScreenshot"],
                upload_dump=artifact_policy["uploadDump"],
            ),
        ),
        allowed_task_types=list(catalog["allowedTaskTypes"]),
    )


def caller_context_payload(caller_context: CallerContext) -> dict[str, str]:
    return {
        "agentTaskId": caller_context.agent_task_id,
        "turnId": caller_context.turn_id,
        "stepId": caller_context.step_id,
    }


def map_catalog_item(item: dict[str, Any]) -> ToolCatalogItem:
    governance = item.get("governance") or {}
    return ToolCatalogItem(
        name=item["name"],
        title=item.get("title"),
        description=item.get("description"),
        tool_kind=item.get("toolKind", "tool"),
        risk_level=ToolRiskLevel(item.get("riskLevel", ToolRiskLevel.DISCOVERY.value)),
        requires_approval=bool(governance.get("requiresApproval", False)),
        confirmation_mode=governance.get("confirmationMode"),
        input_schema=dict(item.get("inputSchema") or {}),
        semantic_tags=list(item.get("semanticTags") or []),
    )


def map_tool_audit(audit: dict[str, Any] | None) -> ToolAuditRef | None:
    if not audit:
        return None
    return ToolAuditRef(audit_id=audit["auditId"], risk_level=ToolRiskLevel(audit["riskLevel"]))


def map_entity_refs(entity_refs: dict[str, Any] | None) -> PlatformEntityRefs | None:
    if entity_refs is None:
        return None
    return PlatformEntityRefs(
        proposal_id=entity_refs.get("proposalId"),
        run_id=entity_refs.get("runId"),
        run_target_id=entity_refs.get("runTargetId"),
        task_id=entity_refs.get("taskId"),
        attempt_id=entity_refs.get("attemptId"),
        artifact_ids=list(entity_refs.get("artifactIds") or []),
    )


def map_tool_error(error_payload: dict[str, Any] | None) -> ToolExecutionError | None:
    if not error_payload:
        return None
    return ToolExecutionError(
        code=error_payload.get("code", "UNKNOWN_ERROR"),
        message=error_payload.get("message", error_payload.get("code", "UNKNOWN_ERROR")),
        retryable=bool(error_payload.get("retryable", False)),
    )


def map_attempt_context(attempt: dict[str, Any]) -> AttemptContext:
    return AttemptContext(
        attempt_id=attempt["attemptId"],
        task_id=attempt["taskId"],
        device_id=attempt["deviceId"],
        run_id=attempt["runId"],
        status=attempt["status"],
        final_state=attempt.get("finalState"),
        failure_reason=attempt.get("failureReason"),
        started_at=attempt.get("startedAt"),
        finished_at=attempt.get("finishedAt"),
        created_at=attempt.get("createdAt"),
        updated_at=attempt.get("updatedAt"),
    )


def map_run_counts(counts: dict[str, Any]) -> RunCounts:
    return RunCounts(
        total_targets=counts.get("totalTargets", 0),
        queued=counts.get("queued", 0),
        running=counts.get("running", 0),
        retry_pending=counts.get("retryPending", 0),
        succeeded=counts.get("succeeded", 0),
        failed=counts.get("failed", 0),
        cancelled=counts.get("cancelled", 0),
    )


def map_run_attempt_counts(counts: dict[str, Any]) -> RunAttemptCounts:
    return RunAttemptCounts(
        total=counts.get("total", 0),
        running=counts.get("running", 0),
        failed=counts.get("failed", 0),
        succeeded=counts.get("succeeded", 0),
    )


def map_run_summary_context(run: dict[str, Any]) -> RunSummaryContext:
    return RunSummaryContext(
        run_id=run["runId"],
        name=run["name"],
        description=run.get("description"),
        pool_id=run.get("poolId"),
        status=run["status"],
        final_state=run.get("finalState"),
        task_type=run["taskType"],
        profile_package=run.get("profilePackage"),
        priority=run.get("priority"),
        labels=list(run.get("labels") or []),
        source=run.get("source"),
        created_by=run.get("createdBy"),
        max_retries_per_device=run.get("maxRetriesPerDevice"),
        queue_timeout_ms=run.get("queueTimeoutMs"),
        cancel_requested=bool(run.get("cancelRequested", False)),
        created_at=run.get("createdAt"),
        updated_at=run.get("updatedAt"),
        started_at=run.get("startedAt"),
        finished_at=run.get("finishedAt"),
        counts=map_run_counts(run.get("counts") or {}),
    )


def map_attempt_artifact_resource(artifact: dict[str, Any]) -> AttemptArtifactResource:
    resource = artifact.get("resource") or {}
    return AttemptArtifactResource(
        artifact_id=artifact["artifactId"],
        attempt_id=artifact["attemptId"],
        task_id=artifact["taskId"],
        run_id=artifact["runId"],
        artifact_type=artifact["artifactType"],
        file_name=artifact["fileName"],
        mime_type=artifact.get("mimeType"),
        size_bytes=artifact.get("sizeBytes"),
        created_at=artifact["createdAt"],
        resource_handle=resource.get("handle"),
    )


def map_run_detail_context(detail: dict[str, Any]) -> RunDetailContext:
    return RunDetailContext(
        run=map_run_summary_context(detail.get("run") or {}),
        task_payload=dict(detail.get("taskPayload") or {}),
        run_config=dict(detail.get("runConfig") or {}),
        artifact_policy=dict(detail.get("artifactPolicy") or {}),
        targets=[map_run_target_context(target) for target in detail.get("targets") or []],
    )


def map_run_governance_snapshot(result: dict[str, Any]) -> RunGovernanceSnapshot:
    return RunGovernanceSnapshot(
        run_id=result["runId"],
        status=result["status"],
        target_counts=map_run_counts(result.get("targetCounts") or {}),
        attempt_counts=map_run_attempt_counts(result.get("attemptCounts") or {}),
        latest_attempt_ids=list(result.get("latestAttemptIds") or []),
        blockers=list(result.get("blockers") or []),
        last_updated_at=result["lastUpdatedAt"],
    )


def map_run_lineage_snapshot(result: dict[str, Any]) -> RunLineageSnapshot:
    return RunLineageSnapshot(
        run_id=result["runId"],
        run=map_run_detail_context(result.get("run") or {}),
        targets=[map_run_target_context(target) for target in result.get("targets") or []],
        attempts=[map_attempt_context(attempt) for attempt in result.get("attempts") or []],
        latest_artifacts=[map_attempt_artifact_resource(artifact) for artifact in result.get("latestArtifacts") or []],
        audit_refs=[map_audit_entry(entry) for entry in result.get("auditRefs") or []],
        blockers=list(result.get("blockers") or []),
        current_governed_options=list(result.get("currentGovernedOptions") or []),
    )


def map_run_target_context(run_target: dict[str, Any]) -> RunTargetContext:
    latest_attempt = run_target.get("latestAttempt")
    return RunTargetContext(
        run_target_id=run_target["runTargetId"],
        device_id=run_target["deviceId"],
        sequence_id=run_target.get("sequenceId"),
        status=run_target["status"],
        attempt_count=run_target["attemptCount"],
        current_task_id=run_target.get("currentTaskId"),
        latest_attempt_id=run_target.get("latestAttemptId"),
        failure_reason=run_target.get("failureReason"),
        started_at=run_target.get("startedAt"),
        finished_at=run_target.get("finishedAt"),
        latest_attempt=map_attempt_context(latest_attempt) if latest_attempt else None,
    )


def map_failure_triage_record(result: dict[str, Any]) -> FailureTriageRecord:
    triage_result = result.get("result") or {}
    validation = result.get("validation") or {}
    return FailureTriageRecord(
        triage_result_id=result["triageResultId"],
        run_target_id=result["runTargetId"],
        failure_category=FailureCategory(triage_result["failureCategory"]),
        probable_cause=triage_result["probableCause"],
        confidence=triage_result["confidence"],
        retry_recommendation=RetryRecommendation(triage_result["retryRecommendation"]),
        suggested_next_action=SuggestedNextAction(triage_result["suggestedNextAction"]),
        operator_review_hints=list(triage_result.get("operatorReviewHints") or []),
        evidence=list(triage_result.get("evidence") or []),
        validation=FailureTriageValidation(
            valid=bool(validation.get("valid", False)),
            errors=list(validation.get("errors") or []),
            warnings=list(validation.get("warnings") or []),
        ),
        model_meta=dict(result.get("modelMeta") or {}),
        generated_at=result["generatedAt"],
    )


def map_recovery_guidance(result: dict[str, Any]) -> RecoveryGuidance:
    return RecoveryGuidance(
        entity_kind=result["entityKind"],
        entity_id=result["entityId"],
        allowed_actions=list(result.get("allowedActions") or []),
        recommended_action=result["recommendedAction"],
        requires_approval=bool(result["requiresApproval"]),
        required_inputs=list(result.get("requiredInputs") or []),
        prerequisites=list(result.get("prerequisites") or []),
        stop_conditions=list(result.get("stopConditions") or []),
        stop_conditions_summary=result["stopConditionsSummary"],
        why_not_others=result["whyNotOthers"],
        explanation=result["explanation"],
        confidence=result["confidence"],
    )


def map_governed_action_result(
    response: dict[str, Any],
    proposal_id: str,
    action_tool_name: str,
) -> GovernedActionResult:
    status = response.get("status")
    state = {
        "approval_required": GovernedActionState.APPROVAL_REQUIRED,
        "completed": GovernedActionState.EXECUTED,
        "failed": GovernedActionState.FAILED,
    }[status]
    confirmation = response.get("confirmation") or {}
    return GovernedActionResult(
        state=state,
        proposal_id=proposal_id,
        action_tool_name=action_tool_name,
        audit=map_tool_audit(response.get("audit")),
        entity_refs=map_entity_refs(response.get("entityRefs")),
        confirmation_id=confirmation.get("confirmationId"),
        confirmation_summary=confirmation.get("summary"),
        confirmation_expires_at=confirmation.get("expiresAt"),
        result=response.get("result") or {},
        warnings=list(response.get("warnings") or []),
        error=map_tool_error(response.get("error")),
    )


def map_audit_entry(entry: dict[str, Any]) -> AuditTimelineEntry:
    return AuditTimelineEntry(
        audit=ToolAuditRef(
            audit_id=entry["auditId"],
            risk_level=ToolRiskLevel(entry["riskLevel"]),
        ),
        request_id=entry.get("requestId"),
        session_id=entry.get("sessionId"),
        tool=entry["tool"],
        status=entry["status"],
        caller_context={
            "agentTaskId": (entry.get("callerContext") or {}).get("agentTaskId"),
            "turnId": (entry.get("callerContext") or {}).get("turnId"),
            "stepId": (entry.get("callerContext") or {}).get("stepId"),
        },
        entity_refs=map_entity_refs(entry.get("entityRefs")) or PlatformEntityRefs(),
        created_at=entry["createdAt"],
        updated_at=entry["updatedAt"],
    )


__all__ = [
    "caller_context_payload",
    "map_attempt_artifact_resource",
    "map_attempt_context",
    "map_audit_entry",
    "map_catalog_item",
    "map_dispatch_device_context",
    "map_entity_refs",
    "map_failure_triage_record",
    "map_governed_action_result",
    "map_recovery_guidance",
    "map_run_planning_catalog_context",
    "map_run_attempt_counts",
    "map_run_counts",
    "map_run_detail_context",
    "map_run_governance_snapshot",
    "map_run_lineage_snapshot",
    "map_run_summary_context",
    "map_run_target_context",
    "map_tool_audit",
    "map_tool_error",
    "require_completed_tool_result",
    "require_completed_tool_payload",
]
