from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from mobiflow_agent.collection import (
    CollectionDispatchService,
    CollectionDispatchStatus,
    CollectionIntent,
    DispatchEntry,
    DispatchPlan,
    DispatchPlanCompiler,
    ExplicitDeviceSelector,
    IntentPlanningResult,
    TaggedDeviceSelector,
)
from mobiflow_agent.platform.adapter import PlatformAdapterError
from mobiflow_agent.platform.types import (
    AvailableProfileContext,
    DispatchDeviceContext,
    GovernedActionResult,
    GovernedActionState,
    PlatformArtifactPolicy,
    PlatformEntityRefs,
    PlatformRunConfig,
    RunPlanningCatalogContext,
    RunPlanningDefaultPolicy,
    ToolExecutionError,
)
from mobiflow_agent.runtime.state import CallerContext
from mobiflow_agent.waypoint import SequenceCatalog


def _device(device_id: str = "dev-7") -> DispatchDeviceContext:
    return DispatchDeviceContext(
        device_id=device_id,
        installed_profiles=["com.tencent.mm"],
        tags=["android13"],
        registered=True,
        online=True,
        busy=False,
        status="IDLE",
        updated_at=1721550000000,
    )


def _catalog() -> RunPlanningCatalogContext:
    return RunPlanningCatalogContext(
        available_device_pools=[],
        available_profiles=[
            AvailableProfileContext(
                profile_package="com.tencent.mm",
                installed_device_count=1,
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


def _plan(sequence_id: str = "wechat.text_chat.v1") -> DispatchPlan:
    return DispatchPlan(
        name="collection",
        dispatch=[
            DispatchEntry(
                sequence_id=sequence_id,
                select=ExplicitDeviceSelector(device_ids=["dev-7"]),
            )
        ],
    )


def _caller() -> CallerContext:
    return CallerContext(
        session_id="session-1",
        agent_task_id="task-1",
        turn_id="turn-1",
        step_id="step-1",
    )


@dataclass
class FakePlatform:
    governed_result: GovernedActionResult
    discovery_error: PlatformAdapterError | None = None
    calls: list[str] = field(default_factory=list)

    def list_devices(self):
        self.calls.append("list_devices")
        if self.discovery_error is not None:
            raise self.discovery_error
        return [_device()]

    def get_run_planning_catalog(self):
        self.calls.append("get_run_planning_catalog")
        return _catalog()

    def submit_execution_proposal(self, proposal, caller_context):
        self.calls.append("submit_execution_proposal")
        return self.governed_result


@dataclass
class StubPlanner:
    result: IntentPlanningResult
    calls: int = 0

    def plan(self, intent, **kwargs):
        self.calls += 1
        return self.result


def _governed(state: GovernedActionState) -> GovernedActionResult:
    values = {
        "state": state,
        "proposal_id": "collection-dispatch:session-1:turn-1",
        "action_tool_name": "create_heterogeneous_run",
    }
    if state == GovernedActionState.APPROVAL_REQUIRED:
        values["confirmation_id"] = "confirm-1"
        values["entity_refs"] = PlatformEntityRefs(proposal_id=values["proposal_id"])
    elif state == GovernedActionState.EXECUTED:
        values["entity_refs"] = PlatformEntityRefs(
            proposal_id=values["proposal_id"], run_id="run-1"
        )
    else:
        values["error"] = ToolExecutionError(
            code="RUN_REJECTED", message="run rejected", retryable=False
        )
    return GovernedActionResult(**values)


def _service(platform, planning_result) -> CollectionDispatchService:
    return CollectionDispatchService(
        platform=platform,
        sequence_catalog=SequenceCatalog.default(),
        intent_planner=StubPlanner(planning_result),
        compiler=DispatchPlanCompiler(),
    )


def test_plan_intent_discovers_plans_and_compiles_without_submitting() -> None:
    platform = FakePlatform(_governed(GovernedActionState.APPROVAL_REQUIRED))
    planning = IntentPlanningResult(
        status=CollectionDispatchStatus.PLANNED,
        plan=_plan(),
        confidence=0.8,
        trace_refs=["trace-1", "trace-1"],
    )

    result = _service(platform, planning).plan_intent(
        CollectionIntent(raw_text="collect on dev-7"), _caller()
    )

    assert result.status == CollectionDispatchStatus.PLANNED
    assert result.plan == planning.plan
    assert result.proposal is not None and result.proposal.confidence == 0.8
    assert result.trace_refs == ["trace-1"]
    assert platform.calls == ["list_devices", "get_run_planning_catalog"]


def test_plan_intent_returns_clarification_without_compiling_or_submitting() -> None:
    platform = FakePlatform(_governed(GovernedActionState.APPROVAL_REQUIRED))
    planning = IntentPlanningResult(
        status=CollectionDispatchStatus.NEEDS_CLARIFICATION,
        clarification_questions=["需要多少台设备？"],
    )

    result = _service(platform, planning).submit_intent(
        CollectionIntent(raw_text="collect"), _caller()
    )

    assert result.status == CollectionDispatchStatus.NEEDS_CLARIFICATION
    assert result.clarification_questions == ["需要多少台设备？"]
    assert "submit_execution_proposal" not in platform.calls


def test_discovery_error_becomes_typed_error_with_retryability() -> None:
    platform = FakePlatform(
        _governed(GovernedActionState.APPROVAL_REQUIRED),
        discovery_error=PlatformAdapterError("INVENTORY_DOWN", "try later", retryable=True),
    )
    result = _service(
        platform,
        IntentPlanningResult(
            status=CollectionDispatchStatus.NEEDS_CLARIFICATION,
            clarification_questions=["unused"],
        ),
    ).plan_intent(CollectionIntent(raw_text="collect"), _caller())

    assert result.status == CollectionDispatchStatus.ERROR
    assert result.issues == ["platform_error:INVENTORY_DOWN:retryable=true:try later"]
    assert platform.calls == ["list_devices"]


@pytest.mark.parametrize(
    ("governed_state", "dispatch_status"),
    [
        (GovernedActionState.APPROVAL_REQUIRED, CollectionDispatchStatus.APPROVAL_REQUIRED),
        (GovernedActionState.EXECUTED, CollectionDispatchStatus.EXECUTED),
        (GovernedActionState.FAILED, CollectionDispatchStatus.FAILED),
    ],
)
def test_submit_intent_maps_governed_result_once(governed_state, dispatch_status) -> None:
    platform = FakePlatform(_governed(governed_state))
    planning = IntentPlanningResult(
        status=CollectionDispatchStatus.PLANNED,
        plan=_plan(),
        confidence=0.8,
    )

    result = _service(platform, planning).submit_intent(
        CollectionIntent(raw_text="collect"), _caller()
    )

    assert result.status == dispatch_status
    assert result.governed_result is not None
    assert platform.calls.count("submit_execution_proposal") == 1
    assert "resolve_approval" not in platform.calls
    if governed_state == GovernedActionState.APPROVAL_REQUIRED:
        assert result.governed_result.confirmation_id == "confirm-1"
    if governed_state == GovernedActionState.EXECUTED:
        assert result.governed_result.entity_refs.run_id == "run-1"
    if governed_state == GovernedActionState.FAILED:
        assert result.governed_result.error.code == "RUN_REJECTED"


def test_submit_plan_skips_model_but_not_compilation_or_governance() -> None:
    platform = FakePlatform(_governed(GovernedActionState.APPROVAL_REQUIRED))
    planner = StubPlanner(
        IntentPlanningResult(
            status=CollectionDispatchStatus.NEEDS_CLARIFICATION,
            clarification_questions=["must not be called"],
        )
    )
    service = CollectionDispatchService(
        platform=platform,
        sequence_catalog=SequenceCatalog.default(),
        intent_planner=planner,
        compiler=DispatchPlanCompiler(),
    )

    result = service.submit_plan(
        CollectionIntent(raw_text="structured"), _plan(), _caller()
    )

    assert planner.calls == 0
    assert result.status == CollectionDispatchStatus.APPROVAL_REQUIRED
    assert result.proposal is not None and result.proposal.confidence == 1.0
    assert platform.calls == [
        "list_devices",
        "get_run_planning_catalog",
        "submit_execution_proposal",
    ]


def test_submit_plan_cannot_bypass_compiler_validation() -> None:
    platform = FakePlatform(_governed(GovernedActionState.APPROVAL_REQUIRED))
    result = _service(
        platform,
        IntentPlanningResult(
            status=CollectionDispatchStatus.NEEDS_CLARIFICATION,
            clarification_questions=["unused"],
        ),
    ).submit_plan(
        CollectionIntent(raw_text="structured"), _plan("wechat.unknown.v1"), _caller()
    )

    assert result.status == CollectionDispatchStatus.REJECTED
    assert "unknown_sequence:wechat.unknown.v1" in result.issues
    assert "submit_execution_proposal" not in platform.calls
