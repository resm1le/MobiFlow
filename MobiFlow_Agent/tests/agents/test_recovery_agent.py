from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.common.contracts import EntityKind
from mobiflow_agent.execution.recovery.triage import FailureTriageGuidanceService
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.platform.adapter import FakePlatformAdapter
from mobiflow_agent.platform.types import (
    AttemptContext,
    FailureCategory,
    FailureTriageRecord,
    FailureTriageValidation,
    RecoveryGuidance,
    RetryRecommendation,
    RunTargetContext,
    SuggestedNextAction,
)
from mobiflow_agent.task.session import TaskSession


def test_recovery_agent_uses_triage_service_for_run_target_sessions() -> None:
    agent = RecoveryAgent(
        triage_service=FailureTriageGuidanceService(
            FakePlatformAdapter(
                run_targets={
                    "rt-1": RunTargetContext(
                        run_target_id="rt-1",
                        device_id="device-1",
                        status="FAILED",
                        attempt_count=1,
                        latest_attempt=AttemptContext(
                            attempt_id="attempt-1",
                            task_id="task-1",
                            device_id="device-1",
                            run_id="run-1",
                            status="FAILED",
                        ),
                    )
                },
                generated_failure_triage=[
                    FailureTriageRecord(
                        triage_result_id="triage-1",
                        run_target_id="rt-1",
                        failure_category=FailureCategory.UI_NOT_FOUND,
                        probable_cause="Login button was not visible.",
                        confidence=0.8,
                        retry_recommendation=RetryRecommendation.INSPECT_PROFILE,
                        suggested_next_action=SuggestedNextAction.INSPECT_ARTIFACTS,
                        validation=FailureTriageValidation(valid=True),
                        generated_at=1710000000000,
                    )
                ],
                recovery_guidance={
                    "run-1": RecoveryGuidance(
                        entity_kind="run",
                        entity_id="run-1",
                        allowed_actions=["cancel_run"],
                        recommended_action="cancel_run",
                        requires_approval=True,
                        stop_conditions_summary="Stop on approval.",
                        why_not_others="The run is blocked.",
                        explanation="Cancel is the governed action.",
                        confidence=0.9,
                    )
                },
            )
        )
    )
    session = TaskSession(
        session_id="session-1",
        goal="Recover blocked target",
        target_kind=EntityKind.RUN_TARGET,
        target_id="rt-1",
    )

    outcome, result = agent.recover(session, None)

    assert outcome.guidance is not None
    assert outcome.guidance.recommended_action == "cancel_run"
    assert outcome.execution_context is not None
    assert outcome.execution_context.action_name == "cancel_run"
    assert outcome.verification_spec is not None
    assert "cancel_run" in outcome.summary
    assert result.payload["recovery_outcome"]["guidance"]["recommended_action"] == "cancel_run"


def test_recovery_agent_can_return_model_driven_recovery_outcome() -> None:
    session = TaskSession(
        session_id="session-1",
        goal="Recover blocked run",
        target_kind=EntityKind.RUN,
        target_id="run-1",
        active_model_profile="recovery-profile",
    )
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="recovery-profile", provider="noop", model="noop-model")],
            clients={
                "noop": NoopModelClient(
                    responses=[
                        {
                            "summary": "Recovery recommends a guarded retry.",
                            "target_kind": "run",
                            "target_id": "run-1",
                            "evidence_refs": [
                                {
                                    "evidence_id": "recovery-evidence-1",
                                    "kind": "inline_note",
                                    "summary": "Recovery reasoning note.",
                                    "locator": "run-1",
                                }
                            ],
                        }
                    ]
                )
            },
        ),
        role_policy=RoleModelPolicy(role_profiles={"recovery": "recovery-profile"}),
    )

    outcome, result = RecoveryAgent(model_client=runtime).recover(session, None)

    assert outcome.summary == "Recovery recommends a guarded retry."
    assert result.payload["model_trace_refs"]
    assert len(session.model_trace) == 1
