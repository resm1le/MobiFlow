from __future__ import annotations

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.collection import (
    CollectionDispatchStatus,
    CollectionIntent,
    IntentPlanner,
    IntentPlannerPromptBuilder,
)
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.platform.types import (
    AvailableProfileContext,
    DispatchDeviceContext,
    PlatformArtifactPolicy,
    PlatformRunConfig,
    RunPlanningCatalogContext,
    RunPlanningDefaultPolicy,
)
from mobiflow_agent.waypoint import SequenceCatalog


def _devices() -> list[DispatchDeviceContext]:
    return [
        DispatchDeviceContext(
            device_id=device_id,
            installed_profiles=["com.tencent.mm"],
            tags=["android13"],
            registered=True,
            online=True,
            busy=False,
            status="IDLE",
            updated_at=1721550000000,
        )
        for device_id in ["dev-7", "dev-9", "dev-10"]
    ]


def _planning_catalog() -> RunPlanningCatalogContext:
    return RunPlanningCatalogContext(
        available_device_pools=[],
        available_profiles=[
            AvailableProfileContext(
                profile_package="com.tencent.mm",
                installed_device_count=3,
                supported_task_types=["PLUGIN_RUN"],
            )
        ],
        default_run_policy=RunPlanningDefaultPolicy(
            priority=100,
            max_retries_per_device=0,
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
        allowed_task_types=["PLUGIN_RUN"],
    )


def _runtime(response) -> ModelRuntime:
    return ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="planner-profile", provider="noop", model="noop")],
            clients={"noop": NoopModelClient(responses=[response])},
        ),
        role_policy=RoleModelPolicy(
            role_profiles={AgentRole.PLANNER.value: "planner-profile"}
        ),
    )


def _plan_decision(sequence_id: str = "wechat.text_chat.v1") -> dict:
    return {
        "decision_type": "plan",
        "plan": {
            "name": "mixed collection",
            "description": "text chat and video call",
            "dispatch": [
                {
                    "sequence_id": sequence_id,
                    "select": {"count": 3, "required_tags": ["android13"]},
                },
                {
                    "sequence_id": "wechat.video_call.v1",
                    "select": {"device_ids": ["dev-7", "dev-9"]},
                },
            ],
        },
        "clarification_questions": [],
        "confidence": 0.91,
    }


def test_prompt_contains_only_bounded_planning_context_and_rules() -> None:
    intent = CollectionIntent(raw_text="3 text chats on android13")
    prompt = IntentPlannerPromptBuilder().build(
        intent=intent,
        sequences=SequenceCatalog.default().list_sequences(),
        devices=_devices(),
        planning_catalog=_planning_catalog(),
    )

    assert prompt.context_payload["intent"]["raw_text"] == intent.raw_text
    assert prompt.context_payload["sequence_catalog"][0]["waypoint_ids"]
    assert prompt.context_payload["device_inventory"][0]["device_id"] == "dev-7"
    assert prompt.context_payload["observed_tags"] == ["android13"]
    assert prompt.context_payload["planning_catalog"]["allowed_task_types"] == ["PLUGIN_RUN"]
    assert prompt.context_payload["selector_contract"]["exactly_one"] is True
    for rule in [".vN", "CLARIFY", "draft_sequence", "approval", "run configuration"]:
        assert rule in prompt.system_prompt


def test_planner_maps_explicit_mixed_intent_and_preserves_trace() -> None:
    result = IntentPlanner(model_runtime=_runtime(_plan_decision())).plan(
        CollectionIntent(raw_text="3 text chats on android13 plus video on dev-7/dev-9"),
        sequence_catalog=SequenceCatalog.default(),
        devices=_devices(),
        planning_catalog=_planning_catalog(),
    )

    assert result.status == CollectionDispatchStatus.PLANNED
    assert result.plan is not None and len(result.plan.dispatch) == 2
    assert result.confidence == 0.91
    assert len(result.trace_refs) == 1
    assert result.trace_refs[0].startswith("model-invocation:")


def test_planner_preserves_clarification_decision() -> None:
    result = IntentPlanner(
        model_runtime=_runtime(
            {
                "decision_type": "clarify",
                "plan": None,
                "clarification_questions": ["需要多少台设备？"],
                "confidence": 0.4,
            }
        )
    ).plan(
        CollectionIntent(raw_text="collect text chats"),
        sequence_catalog=SequenceCatalog.default(),
        devices=_devices(),
        planning_catalog=_planning_catalog(),
    )

    assert result.status == CollectionDispatchStatus.NEEDS_CLARIFICATION
    assert result.plan is None
    assert result.clarification_questions == ["需要多少台设备？"]
    assert result.confidence == 0.4
    assert result.trace_refs


def test_planner_normalizes_missing_runtime_and_invalid_model_output() -> None:
    kwargs = {
        "sequence_catalog": SequenceCatalog.default(),
        "devices": _devices(),
        "planning_catalog": _planning_catalog(),
    }
    missing = IntentPlanner().plan(CollectionIntent(raw_text="collect"), **kwargs)
    invalid = IntentPlanner(model_runtime=_runtime({"unexpected": True})).plan(
        CollectionIntent(raw_text="collect"), **kwargs
    )

    assert missing.status == CollectionDispatchStatus.NEEDS_CLARIFICATION
    assert missing.issues == ["intent_planner_model_runtime_missing"]
    assert invalid.status == CollectionDispatchStatus.NEEDS_CLARIFICATION
    assert invalid.issues == ["intent_planner_model_error"]


def test_planner_does_not_reject_schema_valid_unknown_sequence() -> None:
    result = IntentPlanner(
        model_runtime=_runtime(_plan_decision("wechat.unknown.v1"))
    ).plan(
        CollectionIntent(raw_text="use the unknown sequence on 3 devices"),
        sequence_catalog=SequenceCatalog.default(),
        devices=_devices(),
        planning_catalog=_planning_catalog(),
    )

    assert result.status == CollectionDispatchStatus.PLANNED
    assert result.plan is not None
    assert result.plan.dispatch[0].sequence_id == "wechat.unknown.v1"
