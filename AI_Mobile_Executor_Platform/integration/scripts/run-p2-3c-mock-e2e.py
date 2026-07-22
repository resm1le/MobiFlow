#!/usr/bin/env python3
"""Run the governed P2-3c smoke with signed, device-free Executor mocks."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any


PLATFORM_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PLATFORM_ROOT.parent
sys.path.insert(0, str(REPOSITORY_ROOT / "MobiFlow_Agent"))
sys.path.insert(0, str(PLATFORM_ROOT))

from integration.mock_executor import (  # noqa: E402
    MockAttemptOutcome,
    MockDevice,
    MockExecutorClient,
    MockExecutorScenario,
)
from mobiflow_agent.collection import (  # noqa: E402
    CollectionDispatchService,
    CollectionDispatchStatus,
    CollectionIntent,
    DispatchEntry,
    DispatchPlan,
    DispatchPlanCompiler,
    ExplicitDeviceSelector,
    IntentPlanner,
)
from mobiflow_agent.platform.adapter import HttpPlatformAdapter  # noqa: E402
from mobiflow_agent.platform.adapter.transport import PROTOCOL_VERSION  # noqa: E402
from mobiflow_agent.runtime.state import CallerContext  # noqa: E402
from mobiflow_agent.waypoint import SequenceCatalog  # noqa: E402


SIMULATION_NOTICE = "SIMULATED EXECUTOR - NO DEVICE UI EXECUTED"
DEFAULT_FIXTURE = PLATFORM_ROOT / "integration/payloads/p2-3c-mock-scenario.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("PLATFORM_TOOL_BASE_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument(
        "--bearer-token",
        default=os.environ.get("PLATFORM_TOOL_BEARER_TOKEN"),
    )
    parser.add_argument(
        "--device-tokens-json",
        default=os.environ.get("P2_3C_DEVICE_TOKENS_JSON"),
        help="JSON object mapping mock device IDs to executor HMAC tokens.",
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Explicitly approve and execute the governed run. Without this flag no run is created.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture = load_object(args.fixture)
    tokens = parse_token_map(args.device_tokens_json)
    device_specs = fixture.get("devices")
    if not isinstance(device_specs, list) or not device_specs:
        raise ValueError("scenario fixture must contain a non-empty devices list")

    platform = HttpPlatformAdapter(args.base_url, args.bearer_token)
    executor_client = MockExecutorClient(args.base_url)
    initial_inventory = platform.list_devices()
    initial_profiles = {
        profile.profile_package
        for profile in platform.get_run_planning_catalog().available_profiles
    }
    initial_wechat_devices = {
        device.device_id
        for device in initial_inventory
        if "com.tencent.mm" in device.installed_profiles
    }
    if not initial_wechat_devices and "com.tencent.mm" in initial_profiles:
        raise AssertionError("planning catalog invented com.tencent.mm before mock registration")

    devices: dict[str, MockDevice] = {}
    expected_sequences: dict[str, str] = {}
    outcomes: dict[str, MockAttemptOutcome] = {}
    for spec in device_specs:
        device_id = require_text(spec, "deviceId")
        if device_id not in tokens:
            raise ValueError(f"P2_3C_DEVICE_TOKENS_JSON has no token for {device_id}")
        device = MockDevice(
            device_id=device_id,
            token=tokens[device_id],
            profiles=tuple(require_text_list(spec, "profiles")),
            tags=tuple(require_text_list(spec, "tags")),
        )
        executor_client.register(device)
        devices[device_id] = device
        expected_sequences[device_id] = require_text(spec, "sequenceId")
        outcomes[device_id] = MockAttemptOutcome(require_text(spec, "outcome"))

    discovered = {device.device_id: device for device in platform.list_devices()}
    for device_id in devices:
        assert device_id in discovered, f"registered mock {device_id} was not discoverable"
        assert "com.tencent.mm" in discovered[device_id].installed_profiles
    registered_profiles = {
        profile.profile_package
        for profile in platform.get_run_planning_catalog().available_profiles
    }
    assert "com.tencent.mm" in registered_profiles

    run_key = uuid.uuid4().hex
    caller = CallerContext(
        session_id=f"p2-3c-{run_key}",
        agent_task_id=f"p2-3c-{run_key}",
        turn_id="dispatch",
        step_id="submit",
    )
    plan = DispatchPlan(
        name=str(fixture.get("name") or "P2-3c mock Executor smoke"),
        description=str(fixture.get("description") or SIMULATION_NOTICE),
        dispatch=[
            DispatchEntry(
                sequence_id=expected_sequences[device_id],
                select=ExplicitDeviceSelector(device_ids=[device_id]),
            )
            for device_id in devices
        ],
    )
    service = CollectionDispatchService(
        platform=platform,
        sequence_catalog=SequenceCatalog.default(),
        intent_planner=IntentPlanner(),
        compiler=DispatchPlanCompiler(),
    )
    submitted = service.submit_plan(
        CollectionIntent(
            raw_text="Run the explicit P2-3c simulated Executor scenario.",
            labels=["p2-3c", "simulated_executor"],
        ),
        plan,
        caller,
    )
    assert submitted.status is CollectionDispatchStatus.APPROVAL_REQUIRED, submitted
    assert submitted.governed_result is not None
    confirmation_id = submitted.governed_result.confirmation_id
    assert confirmation_id
    print(SIMULATION_NOTICE)
    print(f"approval_required confirmation_id={confirmation_id}")
    if not args.approve:
        print("prepare-only smoke complete; rerun with --approve to create and execute the run")
        return 0

    approved = platform.resolve_approval(confirmation_id, True, caller)
    assert approved.entity_refs is not None and approved.entity_refs.run_id
    run_id = approved.entity_refs.run_id
    scenario = MockExecutorScenario(
        client=executor_client,
        devices=tuple(devices.values()),
        outcome_by_device=outcomes,
    )
    claimed = {}
    for device_id, device in devices.items():
        task = scenario.run_claimed_attempt(device)
        assert task is not None, f"{device_id} did not receive its pinned task"
        sequence = task.task_payload.get("waypoint_sequence")
        assert isinstance(sequence, dict)
        assert sequence.get("sequence_id") == expected_sequences[device_id]
        assert task.profile_package == "com.tencent.mm"
        claimed[device_id] = task

    lineage = platform.get_run_lineage_snapshot(run_id)
    assert lineage.run.run.status.upper() == "TERMINAL"
    assert lineage.run.run.final_state == "SUCCEEDED"
    assert {target.device_id: target.sequence_id for target in lineage.targets} == expected_sequences
    assert {attempt.attempt_id for attempt in lineage.attempts} == {
        task.attempt_id for task in claimed.values()
    }
    for device_id, task in claimed.items():
        diagnosis = execute_tool(
            args.base_url,
            args.bearer_token,
            "get_attempt_diagnosis_bundle",
            {"attemptId": task.attempt_id},
        )
        events = diagnosis.get("result", {}).get("keyEvents", [])
        waypoint_events = [event for event in events if event.get("eventType") == "WAYPOINT_SEGMENT"]
        expected_count = len(task.task_payload["waypoint_sequence"]["waypoints"])
        assert len(waypoint_events) == expected_count, (
            f"{device_id} expected {expected_count} waypoint events, got {len(waypoint_events)}"
        )
        assert all(event.get("deviceId") == device_id for event in waypoint_events)
        assert all(event.get("attemptId") == task.attempt_id for event in waypoint_events)

    print(f"run_id={run_id} status={lineage.run.run.status} targets={len(lineage.targets)}")
    print(SIMULATION_NOTICE)
    return 0


def execute_tool(base_url: str, bearer_token: str | None, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from mobiflow_agent.platform.adapter.transport import UrlLibToolRuntimeTransport

    transport = UrlLibToolRuntimeTransport(base_url, bearer_token)
    response = transport.request_json("POST", "/tools/execute", {
        "version": PROTOCOL_VERSION,
        "requestId": f"p2-3c:{tool}:{uuid.uuid4().hex}",
        "sessionId": "p2-3c-mock-e2e",
        "tool": tool,
        "arguments": arguments,
        "callerContext": None,
    })
    if response.get("status") != "completed":
        raise AssertionError(f"{tool} did not complete: {response}")
    return response


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def parse_token_map(raw: str | None) -> dict[str, str]:
    if not raw:
        raise ValueError("P2_3C_DEVICE_TOKENS_JSON is required")
    value = json.loads(raw)
    if not isinstance(value, dict) or not value:
        raise ValueError("P2_3C_DEVICE_TOKENS_JSON must be a non-empty JSON object")
    tokens: dict[str, str] = {}
    for device_id, token in value.items():
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValueError("device token keys must be non-blank strings")
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"device token for {device_id} must be non-blank")
        tokens[device_id] = token
    return tokens


def require_text(value: dict[str, Any], key: str) -> str:
    text = value.get(key)
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"scenario {key} must be a non-blank string")
    return text


def require_text_list(value: dict[str, Any], key: str) -> list[str]:
    items = value.get(key)
    if not isinstance(items, list) or not items or not all(isinstance(item, str) and item for item in items):
        raise ValueError(f"scenario {key} must be a non-empty string list")
    return items


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, ValueError) as error:
        print(f"P2-3c smoke failed: {error}", file=sys.stderr)
        raise SystemExit(2) from error
