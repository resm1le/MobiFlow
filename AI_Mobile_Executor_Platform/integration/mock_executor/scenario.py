"""Deterministic protocol scenarios; no Android or UI execution occurs here."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from .client import ExecutorRequestError, MockExecutorClient
from .models import ClaimedTask, MockAttemptOutcome, MockDevice


def build_waypoint_segments(
    task: ClaimedTask,
    outcome: MockAttemptOutcome,
    *,
    start_ms: int,
    failure_index: int = 0,
) -> list[dict[str, object | None]]:
    sequence = task.task_payload.get("waypoint_sequence")
    if not isinstance(sequence, dict):
        raise ValueError("claimed task has no waypoint_sequence")
    behavior_label = sequence.get("behavior_label")
    waypoints = sequence.get("waypoints")
    if not isinstance(behavior_label, str) or not behavior_label:
        raise ValueError("waypoint_sequence has no behavior_label")
    if not isinstance(waypoints, list) or not waypoints:
        raise ValueError("waypoint_sequence has no waypoints")

    successful = outcome is MockAttemptOutcome.SUCCESS
    if not successful and not 0 <= failure_index < len(waypoints):
        raise ValueError("failure_index is outside the waypoint sequence")

    segments: list[dict[str, object | None]] = []
    for index, waypoint in enumerate(waypoints):
        if not isinstance(waypoint, dict) or not isinstance(waypoint.get("waypoint_id"), str):
            raise ValueError("waypoint_sequence contains an invalid waypoint")
        entered_at: int | None = None
        arrived_at: int | None = None
        dwell_ms: int | None = None
        if successful or index < failure_index:
            entered_at = start_ms + index * 1_000
            arrived_at = entered_at + 400
            dwell_ms = 400
        elif index == failure_index:
            entered_at = start_ms + index * 1_000
        segments.append({
            "step_id": waypoint["waypoint_id"],
            "behavior_label": behavior_label,
            "entered_at_ms": entered_at,
            "arrived_at_ms": arrived_at,
            "dwell_ms": dwell_ms,
        })
    return segments


@dataclass
class MockExecutorScenario:
    client: MockExecutorClient
    devices: tuple[MockDevice, ...]
    outcome_by_device: dict[str, MockAttemptOutcome]
    clock_ms: Callable[[], int] = lambda: int(time.time() * 1000)
    max_transport_attempts: int = 2

    def run_claimed_attempt(self, device: MockDevice) -> ClaimedTask | None:
        task = self._bounded_call(lambda: self.client.claim(device))
        if task is None:
            return None
        configured = self.outcome_by_device.get(device.device_id, MockAttemptOutcome.SUCCESS)
        outcome = MockAttemptOutcome.FAILURE if configured is MockAttemptOutcome.FAIL_THEN_SUCCEED else configured
        self._bounded_call(lambda: self.client.start(device, task))
        self._bounded_call(lambda: self.client.events(device, task, [{
            "scenarioId": "simulated_executor",
            "stepIndex": 0,
            "actionIndex": 0,
            "eventType": "SIMULATED_EXECUTION",
            "state": "COMPLETE" if outcome is MockAttemptOutcome.SUCCESS else "FAILED",
            "code": None,
            "message": "SIMULATED EXECUTOR - NO DEVICE UI EXECUTED",
            "ts": self.clock_ms(),
        }]))
        self._bounded_call(lambda: self.client.finish(device, task, outcome))
        segments = build_waypoint_segments(task, outcome, start_ms=self.clock_ms())
        self._bounded_call(
            lambda: self.client.publish_waypoint_segments(device, task.attempt_id, segments)
        )
        return task

    def _bounded_call(self, operation):
        for index in range(self.max_transport_attempts):
            try:
                return operation()
            except ExecutorRequestError as error:
                if not error.retryable or index + 1 == self.max_transport_attempts:
                    raise
        raise AssertionError("bounded retry loop exhausted")
