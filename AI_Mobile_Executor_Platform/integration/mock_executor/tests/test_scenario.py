import unittest

from integration.mock_executor.client import ExecutorRequestError
from integration.mock_executor.models import ClaimedTask, MockAttemptOutcome, MockDevice
from integration.mock_executor.scenario import MockExecutorScenario, build_waypoint_segments


def task():
    return ClaimedTask(
        "dev-7", "task-1", "attempt-1", "run-1", "wechat.text_chat",
        "com.tencent.mm",
        {"waypoint_sequence": {
            "sequence_id": "wechat.text_chat.v1",
            "behavior_label": "wechat_text_chat",
            "waypoints": [
                {"waypoint_id": "logged_in"},
                {"waypoint_id": "chat_open"},
                {"waypoint_id": "message_sent"},
            ],
        }},
        "agent",
        {},
    )


class WaypointScenarioTest(unittest.TestCase):
    def test_success_keeps_sequence_order_and_complete_timings(self):
        segments = build_waypoint_segments(task(), MockAttemptOutcome.SUCCESS, start_ms=1000)

        self.assertEqual(["logged_in", "chat_open", "message_sent"], [s["step_id"] for s in segments])
        self.assertTrue(all(s["arrived_at_ms"] is not None for s in segments))
        self.assertTrue(all(s["dwell_ms"] == 400 for s in segments))

    def test_failure_has_complete_prefix_interrupted_current_and_incomplete_suffix(self):
        segments = build_waypoint_segments(
            task(), MockAttemptOutcome.FAILURE, start_ms=1000, failure_index=1)

        self.assertIsNotNone(segments[0]["arrived_at_ms"])
        self.assertIsNotNone(segments[1]["entered_at_ms"])
        self.assertIsNone(segments[1]["arrived_at_ms"])
        self.assertIsNone(segments[2]["entered_at_ms"])

    def test_runner_retries_retryable_error_with_a_bound(self):
        class StubClient:
            calls = 0

            def claim(self, _device):
                self.calls += 1
                if self.calls == 1:
                    raise ExecutorRequestError("temporary", retryable=True)
                return None

        client = StubClient()
        device = MockDevice("dev-7", "token", ("com.tencent.mm",))
        scenario = MockExecutorScenario(client, (device,), {}, max_transport_attempts=2)

        self.assertIsNone(scenario.run_claimed_attempt(device))
        self.assertEqual(2, client.calls)

    def test_runner_does_not_retry_contract_error(self):
        class StubClient:
            calls = 0

            def claim(self, _device):
                self.calls += 1
                raise ExecutorRequestError("bad request", retryable=False, status=400)

        client = StubClient()
        device = MockDevice("dev-7", "token", ("com.tencent.mm",))
        scenario = MockExecutorScenario(client, (device,), {}, max_transport_attempts=3)

        with self.assertRaises(ExecutorRequestError):
            scenario.run_claimed_attempt(device)
        self.assertEqual(1, client.calls)


if __name__ == "__main__":
    unittest.main()
