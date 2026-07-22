"""Minimal signed HTTP client for the Platform Executor ingress contract."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .models import ClaimedTask, MockAttemptOutcome, MockDevice


@dataclass(frozen=True)
class HttpResult:
    status: int
    body: bytes = b""


class HttpTransport(Protocol):
    def send(self, method: str, url: str, headers: dict[str, str], body: bytes) -> HttpResult: ...


class UrllibTransport:
    def send(self, method: str, url: str, headers: dict[str, str], body: bytes) -> HttpResult:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                return HttpResult(response.status, response.read())
        except urllib.error.HTTPError as error:
            return HttpResult(error.code, error.read())


class ExecutorRequestError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


def canonical_signature(
    token: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> str:
    body_hash = hashlib.sha256(body).hexdigest()
    content = f"{method.upper()}{path}{timestamp}{nonce}{body_hash}".encode("utf-8")
    return hmac.new(token.encode("utf-8"), content, hashlib.sha256).hexdigest()


class MockExecutorClient:
    def __init__(
        self,
        base_url: str,
        *,
        transport: HttpTransport | None = None,
        clock_ms: Callable[[], int] | None = None,
        nonce_factory: Callable[[], str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._transport = transport or UrllibTransport()
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._nonce_factory = nonce_factory or (lambda: uuid.uuid4().hex)

    def register(self, device: MockDevice) -> dict[str, Any]:
        return self._request(device, "POST", "/executor/register", device.identity_payload())

    def heartbeat(self, device: MockDevice, current_attempt_id: str | None = None) -> dict[str, Any]:
        return self._request(
            device,
            "POST",
            "/executor/heartbeat",
            device.identity_payload(current_attempt_id),
        )

    def claim(self, device: MockDevice) -> ClaimedTask | None:
        response = self._request(device, "POST", "/executor/tasks/claim", device.identity_payload())
        if not response.get("hasTask"):
            return None
        task = response.get("task")
        if not isinstance(task, dict):
            raise ExecutorRequestError("claim response omitted task", retryable=False)
        return ClaimedTask.from_response(device.device_id, task)

    def start(self, device: MockDevice, task: ClaimedTask) -> None:
        self._require_task_owner(device, task)
        self._request(device, "POST", f"/executor/tasks/{task.attempt_id}/start", {
            "taskId": task.task_id,
            "attemptId": task.attempt_id,
            "runId": task.run_id,
            "profilePackage": task.profile_package,
            "taskType": task.task_type,
            "source": task.source,
        })

    def events(self, device: MockDevice, task: ClaimedTask, events: list[dict[str, Any]]) -> None:
        self._require_task_owner(device, task)
        canonical_events = []
        for event in events:
            canonical_events.append({
                **event,
                "attemptId": task.attempt_id,
                "taskId": task.task_id,
                "deviceId": device.device_id,
                "runId": task.run_id,
            })
        self._request(
            device,
            "POST",
            f"/executor/tasks/{task.attempt_id}/events",
            {"events": canonical_events},
        )

    def finish(
        self,
        device: MockDevice,
        task: ClaimedTask,
        outcome: MockAttemptOutcome,
        *,
        message: str = "simulated_executor",
    ) -> None:
        self._require_task_owner(device, task)
        if outcome not in (MockAttemptOutcome.SUCCESS, MockAttemptOutcome.FAILURE):
            raise ValueError("finish requires one terminal attempt outcome")
        failure_detail = None
        if outcome is MockAttemptOutcome.FAILURE:
            failure_detail = {
                "failureCode": "SIMULATED_FAILURE",
                "failureStage": "mock_execution",
                "lastError": "deterministic mock failure",
                "capturedAt": self._clock_ms(),
            }
        self._request(device, "POST", f"/executor/tasks/{task.attempt_id}/finish", {
            "taskId": task.task_id,
            "attemptId": task.attempt_id,
            "runId": task.run_id,
            "status": outcome.value,
            "preflightSummary": None,
            "failureDetail": failure_detail,
            "message": message,
        })

    def publish_waypoint_segments(
        self,
        device: MockDevice,
        attempt_id: str,
        segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self._request(
            device,
            "POST",
            f"/executor/tasks/{attempt_id}/waypoint-segments",
            {"waypointSegments": segments},
        )

    def _request(
        self,
        device: MockDevice,
        method: str,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        timestamp = str(self._clock_ms())
        nonce = self._nonce_factory()
        headers = {
            "Content-Type": "application/json",
            "X-Executor-DeviceId": device.device_id,
            "X-Executor-Protocol-Version": device.protocol_version,
            "X-Executor-Timestamp": timestamp,
            "X-Executor-Nonce": nonce,
            "X-Executor-Signature": canonical_signature(
                device.token, method, path, timestamp, nonce, body
            ),
        }
        try:
            result = self._transport.send(method.upper(), self._base_url + path, headers, body)
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            raise ExecutorRequestError(str(error), retryable=True) from error
        if not 200 <= result.status < 300:
            detail = result.body.decode("utf-8", errors="replace")
            raise ExecutorRequestError(
                f"executor request failed with HTTP {result.status}: {detail}",
                retryable=result.status >= 500,
                status=result.status,
            )
        if not result.body:
            return {}
        decoded = json.loads(result.body)
        if not isinstance(decoded, dict):
            raise ExecutorRequestError("executor response must be an object", retryable=False)
        return decoded

    @staticmethod
    def _require_task_owner(device: MockDevice, task: ClaimedTask) -> None:
        if task.device_id != device.device_id:
            raise ValueError("claimed task belongs to a different mock device")
