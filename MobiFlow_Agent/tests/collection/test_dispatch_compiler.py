from __future__ import annotations

from copy import deepcopy

import pytest

from mobiflow_agent.collection import (
    CollectionIntent,
    DispatchEntry,
    DispatchPlan,
    DispatchPlanCompiler,
    ExplicitDeviceSelector,
    TaggedDeviceSelector,
)
from mobiflow_agent.platform.types import (
    AvailableProfileContext,
    DispatchDeviceContext,
    PlatformArtifactPolicy,
    PlatformRunConfig,
    RunPlanningCatalogContext,
    RunPlanningDefaultPolicy,
)
from mobiflow_agent.runtime.state import CallerContext
from mobiflow_agent.waypoint import SequenceCatalog


def _device(device_id: str, **updates) -> DispatchDeviceContext:
    values = {
        "device_id": device_id,
        "installed_profiles": ["com.tencent.mm"],
        "tags": ["android13"],
        "registered": True,
        "online": True,
        "busy": False,
        "status": "IDLE",
        "updated_at": 1721550000000,
    }
    values.update(updates)
    return DispatchDeviceContext(**values)


def _devices() -> list[DispatchDeviceContext]:
    return [_device("dev-7"), _device("dev-9"), _device("dev-10")]


def _planning_catalog(**updates) -> RunPlanningCatalogContext:
    values = {
        "available_device_pools": [],
        "available_profiles": [
            AvailableProfileContext(
                profile_package="com.tencent.mm",
                installed_device_count=3,
                supported_task_types=["PLUGIN_RUN"],
            )
        ],
        "default_run_policy": RunPlanningDefaultPolicy(
            priority=100,
            max_retries_per_device=1,
            queue_timeout_ms=300000,
            default_run_config=PlatformRunConfig(
                loop_count=1,
                budget_ms=300000,
                loop_interval_ms=0,
                network_isolation_enabled=False,
                poll_interval_ms=15000,
                heartbeat_interval_ms=30000,
            ),
            default_artifact_policy=PlatformArtifactPolicy(
                upload_log=True,
                upload_screenshot=True,
                upload_dump=True,
            ),
        ),
        "allowed_task_types": ["PLUGIN_RUN"],
    }
    values.update(updates)
    return RunPlanningCatalogContext(**values)


def _plan() -> DispatchPlan:
    return DispatchPlan(
        name="wechat mixed collection",
        description="3 text chats and 2 video calls",
        dispatch=[
            DispatchEntry(
                sequence_id="wechat.text_chat.v1",
                select=TaggedDeviceSelector(
                    count=3,
                    required_tags=["android13"],
                    excluded_tags=["unstable"],
                ),
            ),
            DispatchEntry(
                sequence_id="wechat.video_call.v1",
                select=ExplicitDeviceSelector(device_ids=["dev-7", "dev-9"]),
            ),
        ],
    )


def _caller() -> CallerContext:
    return CallerContext(
        session_id="session-1",
        agent_task_id="task-1",
        turn_id="turn-1",
        step_id="step-1",
    )


def _compile(
    *,
    intent: CollectionIntent | None = None,
    plan: DispatchPlan | None = None,
    devices: list[DispatchDeviceContext] | None = None,
    planning_catalog: RunPlanningCatalogContext | None = None,
):
    return DispatchPlanCompiler().compile(
        intent or CollectionIntent(raw_text="mixed", labels=["pcap"]),
        plan or _plan(),
        sequence_catalog=SequenceCatalog.default(),
        devices=_devices() if devices is None else devices,
        planning_catalog=planning_catalog or _planning_catalog(),
        caller_context=_caller(),
        planning_confidence=0.91,
    )


def test_compiler_builds_exact_governed_p2_2_payload_without_mutating_inputs() -> None:
    intent = CollectionIntent(raw_text="mixed", labels=["pcap"])
    plan = _plan()
    devices = _devices()
    planning = _planning_catalog()
    before = deepcopy(
        (
            intent.model_dump(mode="json"),
            plan.model_dump(mode="json"),
            [device.model_dump(mode="json") for device in devices],
            planning.model_dump(mode="json"),
        )
    )

    result = _compile(intent=intent, plan=plan, devices=devices, planning_catalog=planning)

    assert result.accepted is True and result.proposal is not None
    proposal = result.proposal
    assert proposal.proposal_id == "collection-dispatch:session-1:turn-1"
    assert proposal.action_tool_name == "create_heterogeneous_run"
    assert proposal.confidence == 0.91
    args = proposal.arguments
    assert args["runConfig"] == {
        "loopCount": 1,
        "budgetMs": 300000,
        "loopIntervalMs": 0,
        "networkIsolationEnabled": False,
        "pollIntervalMs": 15000,
        "heartbeatIntervalMs": 30000,
    }
    assert args["artifactPolicy"] == {
        "uploadLog": True,
        "uploadScreenshot": True,
        "uploadDump": True,
    }
    assert args["labels"] == ["pcap"]
    assert args["source"] == args["createdBy"] == "mobiflow-agent"
    assert [entry["sequenceId"] for entry in args["dispatch"]] == [
        "wechat.text_chat.v1",
        "wechat.video_call.v1",
    ]
    assert args["dispatch"][0]["select"] == {
        "count": 3,
        "requiredTags": ["android13"],
        "excludedTags": ["unstable"],
    }
    assert args["dispatch"][1]["select"] == {"deviceIds": ["dev-7", "dev-9"]}
    for entry in args["dispatch"]:
        resolved = SequenceCatalog.default().resolve_sequence(entry["sequenceId"])
        assert entry["profilePackage"] == resolved.profile_package
        assert entry["taskPayload"]["goal"].strip()
        assert entry["taskPayload"]["waypoint_sequence"] == resolved.model_dump(mode="json")
    assert before == (
        intent.model_dump(mode="json"),
        plan.model_dump(mode="json"),
        [device.model_dump(mode="json") for device in devices],
        planning.model_dump(mode="json"),
    )


@pytest.mark.parametrize(
    ("plan", "intent", "devices", "planning", "issue"),
    [
        (
            DispatchPlan(
                name="unknown",
                dispatch=[DispatchEntry(sequence_id="wechat.unknown.v1", select=TaggedDeviceSelector(count=1))],
            ),
            None,
            None,
            None,
            "unknown_sequence:wechat.unknown.v1",
        ),
        (_plan(), CollectionIntent(raw_text="mixed", task_type="UNKNOWN"), None, None, "unsupported_task_type:UNKNOWN"),
        (_plan(), None, None, _planning_catalog(available_profiles=[]), "profile_unavailable:wechat.text_chat.v1:com.tencent.mm"),
        (_plan(), None, [_device("dev-7"), _device("dev-9", registered=False)], None, "device_not_registered:dev-9"),
        (_plan(), None, [_device("dev-7"), _device("dev-9", installed_profiles=[])], None, "device_profile_missing:dev-9:com.tencent.mm"),
    ],
)
def test_compiler_rejects_stable_contract_errors(plan, intent, devices, planning, issue) -> None:
    result = _compile(intent=intent, plan=plan, devices=devices, planning_catalog=planning)

    assert result.accepted is False
    assert result.proposal is None
    assert issue in result.issues


def test_compiler_rejects_missing_and_cross_dispatch_duplicate_named_devices() -> None:
    plan = DispatchPlan(
        name="duplicates",
        dispatch=[
            DispatchEntry(
                sequence_id="wechat.text_chat.v1",
                select=ExplicitDeviceSelector(device_ids=["dev-7", "missing"]),
            ),
            DispatchEntry(
                sequence_id="wechat.video_call.v1",
                select=ExplicitDeviceSelector(device_ids=["dev-7"]),
            ),
        ],
    )
    result = _compile(plan=plan)

    assert result.accepted is False
    assert "device_not_found:missing" in result.issues
    assert "duplicate_named_device:dev-7" in result.issues


def test_transient_device_and_tag_capacity_conditions_are_warnings_only() -> None:
    devices = [
        _device("dev-7", online=False, busy=True, status="QUIESCED"),
        _device("dev-9", tags=[]),
    ]
    plan = DispatchPlan(
        name="warnings",
        dispatch=[
            DispatchEntry(
                sequence_id="wechat.video_call.v1",
                select=ExplicitDeviceSelector(device_ids=["dev-7"]),
            ),
            DispatchEntry(
                sequence_id="wechat.text_chat.v1",
                select=TaggedDeviceSelector(count=3, required_tags=["android14"]),
            ),
        ],
    )

    result = _compile(plan=plan, devices=devices)

    assert result.accepted is True
    assert any(item.startswith("device_temporarily_unavailable:dev-7") for item in result.warnings)
    assert any(item.startswith("required_tag_unobserved:wechat.text_chat.v1:android14") for item in result.warnings)
    assert any(item.startswith("tag_capacity_snapshot:wechat.text_chat.v1:0/3") for item in result.warnings)
    assert all("Platform revalidates authoritatively when approved" in item for item in result.warnings)


def test_same_caller_turn_produces_stable_proposal_id() -> None:
    assert _compile().proposal.proposal_id == _compile().proposal.proposal_id
