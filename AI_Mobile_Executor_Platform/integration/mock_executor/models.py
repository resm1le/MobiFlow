"""Protocol models used by the mock Executor."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MockAttemptOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILED"
    FAIL_THEN_SUCCEED = "FAIL_THEN_SUCCEED"


@dataclass(frozen=True)
class MockDevice:
    device_id: str
    token: str
    profiles: tuple[str, ...]
    tags: tuple[str, ...] = ()
    protocol_version: str = "v1"
    executor_version: str = "mock-executor/1"
    brand: str = "MobiFlow"
    model: str = "SimulatedExecutor"
    android_version: str = "mock"
    screen_width: int = 1080
    screen_height: int = 2400
    host_group: str = "mock"

    def identity_payload(self, current_attempt_id: str | None = None) -> dict[str, Any]:
        return {
            "deviceId": self.device_id,
            "protocolVersion": self.protocol_version,
            "executorVersion": self.executor_version,
            "brand": self.brand,
            "model": self.model,
            "androidVersion": self.android_version,
            "screenWidth": self.screen_width,
            "screenHeight": self.screen_height,
            "capabilities": {
                "accessibilityEnabled": True,
                "rootAvailable": False,
                "shellAvailable": False,
                "networkIsolationAvailable": False,
                "screenshotCapable": False,
                "uiDumpCapable": False,
            },
            "installedProfiles": list(self.profiles),
            "tags": list(self.tags),
            "hostGroup": self.host_group,
            "healthSnapshot": None,
            "currentAttemptId": current_attempt_id,
        }


@dataclass(frozen=True)
class ClaimedTask:
    device_id: str
    task_id: str
    attempt_id: str
    run_id: str
    task_type: str
    profile_package: str
    task_payload: dict[str, Any]
    source: str
    raw: dict[str, Any] = field(repr=False)

    @classmethod
    def from_response(cls, device_id: str, value: dict[str, Any]) -> "ClaimedTask":
        payload = value.get("taskPayload")
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise ValueError("claim taskPayload must be an object")
        return cls(
            device_id=device_id,
            task_id=str(value["taskId"]),
            attempt_id=str(value["attemptId"]),
            run_id=str(value["runId"]),
            task_type=str(value["taskType"]),
            profile_package=str(value["profilePackage"]),
            task_payload=dict(payload),
            source=str(value.get("source") or "mock_executor"),
            raw=dict(value),
        )
