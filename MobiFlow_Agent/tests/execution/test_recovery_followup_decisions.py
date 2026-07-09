from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision


def test_decision_enum_values_unchanged() -> None:
    assert RecoveryFollowupDriverDecision.SCHEDULE_NEXT.value == "schedule_next"
    assert RecoveryFollowupDriverDecision.HANDOFF_ONLY.value == "handoff_only"
    assert RecoveryFollowupDriverDecision.COMPLETE.value == "complete"
    assert RecoveryFollowupDriverDecision.NO_FOLLOWUP.value == "no_followup"
    assert {m.value for m in RecoveryFollowupDriverDecision} == {
        "schedule_next", "handoff_only", "complete", "no_followup",
    }
