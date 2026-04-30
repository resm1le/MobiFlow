from __future__ import annotations

from dataclasses import dataclass, field

from mobiflow_agent.agents.contracts import StepDecision, StepDecisionType
from mobiflow_agent.common.contracts import EntityKind
from mobiflow_agent.task.session import TaskSession


@dataclass(frozen=True)
class StepPolicyValidationResult:
    accepted: bool
    issues: list[str] = field(default_factory=list)


class StepPolicyDecisionValidator:
    def validate(self, session: TaskSession, decision: StepDecision) -> StepPolicyValidationResult:
        issues: list[str] = []
        step = session.current_step
        if step is None:
            return StepPolicyValidationResult(accepted=False, issues=["missing_current_step"])

        if decision.decision_type == StepDecisionType.PROPOSE_EXECUTION:
            proposal = decision.proposal
            if proposal is None:
                issues.append("missing_proposal")
            else:
                if proposal.action_tool_name not in step.allowed_side_effects:
                    issues.append("proposal_action_not_allowed")
                if not proposal.arguments:
                    issues.append("proposal_missing_arguments")
                expected_kind = step.verification_target_kind or session.target_kind or EntityKind.TASK
                expected_id = step.verification_target_id or session.target_id or session.session_id
                if proposal.target_kind is not None and proposal.target_kind != expected_kind:
                    issues.append("proposal_target_kind_mismatch")
                if proposal.target_id is not None and proposal.target_id != expected_id:
                    issues.append("proposal_target_id_mismatch")

        if decision.decision_type == StepDecisionType.STEP_SUCCEEDED:
            if session.last_observation is None:
                issues.append("success_without_observation")
            elif not self._active_verification_ready(session):
                issues.append("success_without_satisfied_verification")

        if decision.decision_type in {StepDecisionType.REQUEST_REPLAN, StepDecisionType.HANDOFF}:
            if not decision.blocked_reason:
                issues.append("missing_blocked_reason")

        return StepPolicyValidationResult(accepted=not issues, issues=issues)

    @staticmethod
    def _active_verification_ready(session: TaskSession) -> bool:
        from mobiflow_agent.agents.step_policy import StepPolicyAgent

        return StepPolicyAgent._satisfies_active_spec(session)


__all__ = ["StepPolicyDecisionValidator", "StepPolicyValidationResult"]
