import hashlib
import json
import unittest

from integration.mock_executor.client import (
    ExecutorRequestError,
    HttpResult,
    MockExecutorClient,
    canonical_signature,
)
from integration.mock_executor.models import ClaimedTask, MockAttemptOutcome, MockDevice


class FakeTransport:
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    def send(self, method, url, headers, body):
        self.requests.append((method, url, headers, body))
        result = self.results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result


class MockExecutorClientTest(unittest.TestCase):
    def setUp(self):
        self.device = MockDevice("dev-7", "token-fixed", ("com.tencent.mm",), ("android13",))

    def test_hmac_matches_java_fixed_vector(self):
        body = b'{"deviceId":"dev-7"}'
        self.assertEqual(
            "eb3a1fd7370cfe87dddf8b83647ae30047e8b3716e6132c25dd2126a20e8ace5",
            hashlib.sha256(body).hexdigest(),
        )
        self.assertEqual(
            "55aed0e5c8be8b04f51107c70ec6c1ceead173b2a826513014279324539032f0",
            canonical_signature(
                "token-fixed", "POST", "/executor/register",
                "1780000000000", "nonce-fixed", body,
            ),
        )

    def test_register_signs_exact_timestamp_nonce_path_and_body(self):
        transport = FakeTransport([HttpResult(200, b'{"registered":true}')])
        client = MockExecutorClient(
            "http://platform",
            transport=transport,
            clock_ms=lambda: 1780000000000,
            nonce_factory=lambda: "nonce-fixed",
        )

        client.register(self.device)

        method, url, headers, body = transport.requests[0]
        self.assertEqual("POST", method)
        self.assertEqual("http://platform/executor/register", url)
        self.assertEqual("1780000000000", headers["X-Executor-Timestamp"])
        self.assertEqual("nonce-fixed", headers["X-Executor-Nonce"])
        self.assertEqual(
            canonical_signature(
                self.device.token, method, "/executor/register",
                headers["X-Executor-Timestamp"], headers["X-Executor-Nonce"], body,
            ),
            headers["X-Executor-Signature"],
        )

    def test_claim_preserves_empty_payload_without_inventing_lineage(self):
        response = {"hasTask": True, "task": {
            "taskId": "task-1", "attemptId": "attempt-1", "runId": "run-1",
            "taskType": "wechat.text_chat", "profilePackage": "com.tencent.mm",
            "taskPayload": {}, "source": "agent",
        }}
        transport = FakeTransport([HttpResult(200, json.dumps(response).encode())])
        client = MockExecutorClient("http://platform", transport=transport)

        task = client.claim(self.device)

        self.assertIsNotNone(task)
        self.assertEqual({}, task.task_payload)
        self.assertNotIn("runTargetId", task.task_payload)

    def test_heartbeat_and_idle_claim_use_fresh_nonces(self):
        transport = FakeTransport([
            HttpResult(200, b'{"registered":true}'),
            HttpResult(200, b'{"hasTask":false,"task":null}'),
        ])
        nonces = iter(("nonce-1", "nonce-2"))
        client = MockExecutorClient(
            "http://platform", transport=transport, nonce_factory=lambda: next(nonces))

        client.heartbeat(self.device, "attempt-current")
        claimed = client.claim(self.device)

        self.assertIsNone(claimed)
        self.assertEqual("/executor/heartbeat", transport.requests[0][1].removeprefix("http://platform"))
        self.assertEqual("attempt-current", json.loads(transport.requests[0][3])["currentAttemptId"])
        self.assertEqual("/executor/tasks/claim", transport.requests[1][1].removeprefix("http://platform"))
        self.assertEqual(
            ["nonce-1", "nonce-2"],
            [request[2]["X-Executor-Nonce"] for request in transport.requests],
        )

    def test_lifecycle_payloads_derive_identity_from_claim(self):
        transport = FakeTransport([HttpResult(204), HttpResult(204), HttpResult(204), HttpResult(200, b'{"recordedCount":1}')])
        client = MockExecutorClient("http://platform", transport=transport, clock_ms=lambda: 1000)
        task = ClaimedTask(
            "dev-7", "task-1", "attempt-1", "run-1", "wechat.text_chat",
            "com.tencent.mm", {}, "agent", {},
        )

        client.start(self.device, task)
        client.events(self.device, task, [{
            "eventType": "STEP_END", "message": "simulated", "ts": 1000,
        }])
        client.finish(self.device, task, MockAttemptOutcome.SUCCESS)
        client.publish_waypoint_segments(self.device, task.attempt_id, [{
            "step_id": "logged_in", "behavior_label": "wechat_text_chat",
            "entered_at_ms": 1000, "arrived_at_ms": 1400, "dwell_ms": 400,
        }])

        bodies = [json.loads(request[3]) for request in transport.requests]
        self.assertEqual("attempt-1", bodies[0]["attemptId"])
        self.assertEqual("dev-7", bodies[1]["events"][0]["deviceId"])
        self.assertEqual("SUCCEEDED", bodies[2]["status"])
        self.assertEqual({"waypointSegments": bodies[3]["waypointSegments"]}, bodies[3])
        self.assertNotIn("runTargetId", bodies[3])
        self.assertNotIn("deviceId", bodies[3]["waypointSegments"][0])

    def test_4xx_is_not_retryable_and_5xx_is_retryable(self):
        client_4xx = MockExecutorClient(
            "http://platform", transport=FakeTransport([HttpResult(409, b'conflict')]))
        with self.assertRaises(ExecutorRequestError) as caught_4xx:
            client_4xx.register(self.device)
        self.assertFalse(caught_4xx.exception.retryable)

        client_5xx = MockExecutorClient(
            "http://platform", transport=FakeTransport([HttpResult(503, b'unavailable')]))
        with self.assertRaises(ExecutorRequestError) as caught_5xx:
            client_5xx.register(self.device)
        self.assertTrue(caught_5xx.exception.retryable)


if __name__ == "__main__":
    unittest.main()
