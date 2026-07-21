from __future__ import annotations

from mobiflow_agent.collection.models import (
    CollectionIntent,
    DispatchCompilationResult,
    DispatchPlan,
    ExplicitDeviceSelector,
    TaggedDeviceSelector,
)
from mobiflow_agent.common.contracts import ExecutionProposal
from mobiflow_agent.platform.types import (
    DispatchDeviceContext,
    RunPlanningCatalogContext,
)
from mobiflow_agent.runtime.state import CallerContext
from mobiflow_agent.waypoint.catalog import (
    SEQUENCE_ID_PATTERN,
    SequenceCatalog,
    SequenceCatalogError,
)
from mobiflow_agent.waypoint.models import WaypointSequence


_SNAPSHOT_NOTE = "snapshot only; Platform revalidates authoritatively when approved"


class DispatchPlanCompiler:
    def compile(
        self,
        intent: CollectionIntent,
        plan: DispatchPlan,
        *,
        sequence_catalog: SequenceCatalog,
        devices: list[DispatchDeviceContext],
        planning_catalog: RunPlanningCatalogContext,
        caller_context: CallerContext,
        planning_confidence: float,
    ) -> DispatchCompilationResult:
        issues: list[str] = []
        warnings: list[str] = []
        resolved: list[WaypointSequence | None] = []

        if intent.task_type not in planning_catalog.allowed_task_types:
            issues.append(f"unsupported_task_type:{intent.task_type}")

        available_profiles = {
            profile.profile_package for profile in planning_catalog.available_profiles
        }
        devices_by_id = {device.device_id: device for device in devices}
        named_devices: set[str] = set()

        for entry in plan.dispatch:
            sequence = self._resolve(sequence_catalog, entry.sequence_id, issues)
            resolved.append(sequence)
            if sequence is not None and sequence.profile_package not in available_profiles:
                issues.append(
                    f"profile_unavailable:{entry.sequence_id}:{sequence.profile_package}"
                )

            if isinstance(entry.select, ExplicitDeviceSelector):
                for device_id in entry.select.device_ids:
                    if device_id in named_devices:
                        issues.append(f"duplicate_named_device:{device_id}")
                    named_devices.add(device_id)
                    device = devices_by_id.get(device_id)
                    if device is None:
                        issues.append(f"device_not_found:{device_id}")
                        continue
                    if not device.registered:
                        issues.append(f"device_not_registered:{device_id}")
                    if sequence is not None and sequence.profile_package not in device.installed_profiles:
                        issues.append(
                            f"device_profile_missing:{device_id}:{sequence.profile_package}"
                        )
                    transient_states = self._transient_states(device)
                    if transient_states:
                        warnings.append(
                            f"device_temporarily_unavailable:{device_id}:"
                            f"{','.join(transient_states)} ({_SNAPSHOT_NOTE})"
                        )
            elif isinstance(entry.select, TaggedDeviceSelector):
                self._tag_selector_warnings(
                    entry.sequence_id,
                    entry.select,
                    sequence,
                    devices,
                    warnings,
                )
            else:
                issues.append(f"invalid_selector:{entry.sequence_id}")

        if issues:
            return DispatchCompilationResult(
                accepted=False,
                issues=_dedupe(issues),
                warnings=_dedupe(warnings),
            )

        try:
            policy = planning_catalog.default_run_policy
            run_config = policy.default_run_config
            artifact_policy = policy.default_artifact_policy
            dispatch_payload = [
                self._compile_entry(entry, sequence)
                for entry, sequence in zip(plan.dispatch, resolved, strict=True)
                if sequence is not None
            ]
            arguments = {
                "name": plan.name,
                "description": plan.description,
                "taskType": intent.task_type,
                "runConfig": {
                    "loopCount": run_config.loop_count,
                    "budgetMs": run_config.budget_ms,
                    "loopIntervalMs": run_config.loop_interval_ms,
                    "networkIsolationEnabled": run_config.network_isolation_enabled,
                    "pollIntervalMs": run_config.poll_interval_ms,
                    "heartbeatIntervalMs": run_config.heartbeat_interval_ms,
                },
                "artifactPolicy": {
                    "uploadLog": artifact_policy.upload_log,
                    "uploadScreenshot": artifact_policy.upload_screenshot,
                    "uploadDump": artifact_policy.upload_dump,
                },
                "priority": policy.priority,
                "labels": list(intent.labels),
                "source": "mobiflow-agent",
                "createdBy": "mobiflow-agent",
                "maxRetriesPerDevice": policy.max_retries_per_device,
                "queueTimeoutMs": policy.queue_timeout_ms,
                "dispatch": dispatch_payload,
            }
        except (AttributeError, TypeError, ValueError):
            return DispatchCompilationResult(
                accepted=False,
                issues=["invalid_planning_policy"],
                warnings=_dedupe(warnings),
            )

        proposal = ExecutionProposal(
            proposal_id=(
                f"collection-dispatch:{caller_context.session_id}:{caller_context.turn_id}"
            ),
            action_tool_name="create_heterogeneous_run",
            arguments=arguments,
            rationale=(
                "Create one governed heterogeneous collection run from an explicit, "
                "catalog-resolved dispatch plan."
            ),
            preconditions={
                "sequenceIds": [entry.sequence_id for entry in plan.dispatch],
                "deviceInventoryUpdatedAt": max(
                    (device.updated_at for device in devices), default=0
                ),
            },
            expected_observation_changes=[
                "A confirmation is requested before the heterogeneous run is created."
            ],
            confidence=planning_confidence,
        )
        return DispatchCompilationResult(
            accepted=True,
            proposal=proposal,
            warnings=_dedupe(warnings),
        )

    @staticmethod
    def _resolve(
        sequence_catalog: SequenceCatalog,
        sequence_id: str,
        issues: list[str],
    ) -> WaypointSequence | None:
        if not SEQUENCE_ID_PATTERN.fullmatch(sequence_id):
            issues.append(f"invalid_sequence_id:{sequence_id}")
            return None
        try:
            return sequence_catalog.resolve_sequence(sequence_id)
        except SequenceCatalogError:
            issues.append(f"unknown_sequence:{sequence_id}")
            return None

    @staticmethod
    def _compile_entry(entry, sequence: WaypointSequence) -> dict:
        if isinstance(entry.select, ExplicitDeviceSelector):
            selector = {"deviceIds": list(entry.select.device_ids)}
        else:
            selector = {
                "count": entry.select.count,
                "requiredTags": list(entry.select.required_tags),
                "excludedTags": list(entry.select.excluded_tags),
            }
        return {
            "sequenceId": sequence.sequence_id,
            "profilePackage": sequence.profile_package,
            "taskPayload": {
                "goal": (
                    f"Run waypoint sequence {sequence.sequence_id} for behavior "
                    f"{sequence.behavior_label}."
                ),
                "waypoint_sequence": sequence.model_dump(mode="json"),
            },
            "select": selector,
        }

    @staticmethod
    def _transient_states(device: DispatchDeviceContext) -> list[str]:
        states: list[str] = []
        if not device.online:
            states.append("offline")
        if device.busy:
            states.append("busy")
        if device.status.upper() == "QUIESCED":
            states.append("quiesced")
        return states

    @staticmethod
    def _tag_selector_warnings(
        sequence_id: str,
        selector: TaggedDeviceSelector,
        sequence: WaypointSequence | None,
        devices: list[DispatchDeviceContext],
        warnings: list[str],
    ) -> None:
        observed_tags = {tag for device in devices for tag in device.tags}
        for tag in selector.required_tags:
            if tag not in observed_tags:
                warnings.append(
                    f"required_tag_unobserved:{sequence_id}:{tag} ({_SNAPSHOT_NOTE})"
                )
        eligible = [
            device
            for device in devices
            if device.registered
            and device.online
            and not device.busy
            and device.status.upper() != "QUIESCED"
            and set(selector.required_tags).issubset(device.tags)
            and not set(selector.excluded_tags).intersection(device.tags)
            and (
                sequence is None
                or sequence.profile_package in device.installed_profiles
            )
        ]
        if len(eligible) < selector.count:
            warnings.append(
                f"tag_capacity_snapshot:{sequence_id}:{len(eligible)}/{selector.count} "
                f"({_SNAPSHOT_NOTE})"
            )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


__all__ = ["DispatchPlanCompiler"]
