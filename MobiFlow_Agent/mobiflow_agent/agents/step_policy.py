from __future__ import annotations

from typing import Callable

from mobiflow_agent.agents.contracts import AgentRole, RoleRequest, RoleResult, StepDecision, StepDecisionType
from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, ObservationView
from mobiflow_agent.common.ids import build_role_result_id
from mobiflow_agent.model.prompting import StepPolicyPromptBuilder
from mobiflow_agent.model.runtime import ModelRuntime
from mobiflow_agent.task.session import TaskSession

StepPolicyCallback = Callable[[TaskSession], StepDecision]


class StepPolicyAgent:
    def __init__(
        self,
        *,
        model_client: ModelRuntime | None = None,
        prompt_builder: StepPolicyPromptBuilder | None = None,
        step_policy: StepPolicyCallback | None = None,
    ):
        self._model_client = model_client
        self._prompt_builder = prompt_builder or StepPolicyPromptBuilder()
        self._step_policy = step_policy

    def bind_model_runtime(self, model_client: ModelRuntime | None) -> None:
        if model_client is not None:
            self._model_client = model_client

    def decide(self, session: TaskSession, request: RoleRequest | None = None) -> tuple[StepDecision, RoleResult]:
        if request is not None and request.role != AgentRole.STEP_POLICY:
            raise ValueError("StepPolicyAgent received a non-step-policy RoleRequest.")
        before_trace_count = len(session.model_trace)
        decision = self._build_decision(session)
        trace_refs = [
            trace.invocation_id for trace in session.model_trace[before_trace_count:]
        ]
        result = RoleResult(
            result_id=build_role_result_id(),
            role=AgentRole.STEP_POLICY,
            session_id=session.session_id,
            step_id=session.current_step.step_id if session.current_step else None,
            summary=decision.summary,
            payload={
                "step_decision": decision.model_dump(mode="python"),
                "model_trace_refs": trace_refs,
            },
            handoff_reason=decision.decision_type.value,
            next_role=self._next_role(decision),
        )
        return decision, result

    def _build_decision(self, session: TaskSession) -> StepDecision:
        if self._step_policy is not None:
            return self._step_policy(session)
        model_decision = self._decide_with_model(session)
        return model_decision or self._default_decision(session)

    def _decide_with_model(self, session: TaskSession) -> StepDecision | None:
        if self._model_client is None or session.active_model_profile is None:
            return None
        prompt = self._prompt_builder.build(session=session)
        try:
            generated = self._model_client.generate_structured(
                role=AgentRole.STEP_POLICY,
                prompt=prompt,
                response_model=StepDecision,
                profile_name=session.active_model_profile,
                metadata={"session_id": session.session_id},
            )
        except Exception:
            return None
        session.model_trace.append(generated.response.trace)
        return generated.output

    @staticmethod
    def _default_decision(session: TaskSession) -> StepDecision:
        step_id = session.current_step.step_id if session.current_step is not None else session.session_id
        blocked_reason = StepPolicyAgent._step_policy_blocked_reason(session.last_observation)
        if blocked_reason is not None:
            return StepDecision(
                decision_id=f"step-decision:{session.session_id}:{step_id}:request-replan",
                decision_type=StepDecisionType.REQUEST_REPLAN,
                summary=f"Default step policy requested recovery replan: {blocked_reason}.",
                blocked_reason=blocked_reason,
            )
        if StepPolicyAgent._satisfies_active_spec(session):
            return StepDecision(
                decision_id=f"step-decision:{session.session_id}:{step_id}:succeeded",
                decision_type=StepDecisionType.STEP_SUCCEEDED,
                summary="Default step policy found evidence that the dynamic step is ready for verification.",
            )
        proposal = StepPolicyAgent._mobile_proposal(session)
        if proposal is not None:
            return StepDecision(
                decision_id=f"step-decision:{session.session_id}:{step_id}:{proposal.proposal_id}",
                decision_type=StepDecisionType.PROPOSE_EXECUTION,
                summary=f"Default step policy proposed {proposal.action_tool_name}.",
                proposal=proposal,
            )
        return StepDecision(
            decision_id=f"step-decision:{session.session_id}:{step_id}:observe-again",
            decision_type=StepDecisionType.OBSERVE_AGAIN,
            summary="Default step policy needs another observation before deciding.",
        )

    @staticmethod
    def _satisfies_active_spec(session: TaskSession) -> bool:
        observation = session.last_observation
        spec = (
            session.current_step.verification_spec
            if session.current_step is not None and session.current_step.verification_spec is not None
            else session.active_verification_spec
        )
        if observation is None or spec is None:
            return False
        searchable_text = StepPolicyAgent._searchable_text(observation)
        return all(
            StepPolicyAgent._candidate_matches(check.evidence_hint or check.description or check.check_id, searchable_text)
            for check in spec.success_checks
            if check.required
        )

    @staticmethod
    def _mobile_proposal(session: TaskSession) -> ExecutionProposal | None:
        observation = session.last_observation
        if observation is None or session.current_step is None:
            return None
        screen = StepPolicyAgent._screen_snapshot(observation)
        nodes = StepPolicyAgent._ui_nodes(observation)
        allowed = set(session.current_step.allowed_side_effects)
        target_kind = session.current_step.verification_target_kind or session.target_kind or EntityKind.TASK
        target_id = session.current_step.verification_target_id or session.target_id or session.session_id
        screen_id = str(screen.get("screen_id") or "").casefold()
        goal_text = session.goal.casefold()
        metadata = screen.get("metadata") if isinstance(screen.get("metadata"), dict) else {}

        if screen_id == "launcher" and "mobile.launch" in allowed:
            return StepPolicyAgent._proposal(session, "mobile.launch", {"app": "demo"}, target_kind, target_id)
        if StepPolicyAgent._has_node(nodes, "allow_button") and "mobile.tap" in allowed:
            return StepPolicyAgent._proposal(session, "mobile.tap", {"node_id": "allow_button"}, target_kind, target_id)
        if StepPolicyAgent._has_node(nodes, "delete_button") and "delete" in goal_text and "mobile.tap" in allowed:
            return StepPolicyAgent._proposal(session, "mobile.tap", {"node_id": "delete_button"}, target_kind, target_id)
        if StepPolicyAgent._has_node(nodes, "username") and metadata.get("username") != "alice" and "mobile.input_text" in allowed:
            return StepPolicyAgent._proposal(
                session,
                "mobile.input_text",
                {"node_id": "username", "text": "alice"},
                target_kind,
                target_id,
            )
        if StepPolicyAgent._has_node(nodes, "password") and metadata.get("password") != "password entered" and "mobile.input_text" in allowed:
            return StepPolicyAgent._proposal(
                session,
                "mobile.input_text",
                {"node_id": "password", "text": "secret"},
                target_kind,
                target_id,
            )
        if StepPolicyAgent._has_node(nodes, "login_button") and "mobile.tap" in allowed:
            return StepPolicyAgent._proposal(session, "mobile.tap", {"node_id": "login_button"}, target_kind, target_id)
        return None

    @staticmethod
    def _screen_snapshot(observation: ObservationView) -> dict:
        for fact in observation.facts:
            if fact.fact_id == "simulated_screen_snapshot" and isinstance(fact.value, dict):
                return fact.value
        return {}

    @staticmethod
    def _step_policy_blocked_reason(observation: ObservationView | None) -> str | None:
        if observation is None:
            return None
        screen = StepPolicyAgent._screen_snapshot(observation)
        metadata = screen.get("metadata") if isinstance(screen.get("metadata"), dict) else {}
        blocked_reason = metadata.get("step_policy_blocked_reason")
        return blocked_reason if isinstance(blocked_reason, str) and blocked_reason else None

    @staticmethod
    def _ui_nodes(observation: ObservationView) -> list[dict]:
        for fact in observation.facts:
            if fact.fact_id == "simulated_ui_tree" and isinstance(fact.value, list):
                return [node for node in fact.value if isinstance(node, dict)]
        return []

    @staticmethod
    def _has_node(nodes: list[dict], node_id: str) -> bool:
        return any(node.get("node_id") == node_id and node.get("visible", True) for node in nodes)

    @staticmethod
    def _proposal(
        session: TaskSession,
        action_tool_name: str,
        arguments: dict,
        target_kind: EntityKind,
        target_id: str,
    ) -> ExecutionProposal:
        step_id = session.current_step.step_id if session.current_step is not None else "dynamic"
        return ExecutionProposal(
            proposal_id=f"proposal:{session.session_id}:{step_id}:{len(session.step_decisions) + 1}",
            action_tool_name=action_tool_name,
            arguments=arguments,
            target_kind=target_kind,
            target_id=target_id,
            rationale=f"Default dynamic policy selected {action_tool_name}.",
            expected_observation_changes=[action_tool_name],
            confidence=0.7,
        )

    @staticmethod
    def _searchable_text(observation: ObservationView) -> str:
        parts = [observation.observation_id, observation.focus_kind.value, observation.focus_id]
        for fact in observation.facts:
            parts.extend([fact.fact_id, fact.title, str(fact.value)])
            for ref in fact.evidence_refs:
                parts.extend([ref.summary])
                parts.extend(value for value in [ref.locator, ref.handle, ref.uri] if value)
        for inference in observation.inferences:
            parts.extend([inference.inference_id, inference.statement])
        return " ".join(str(part) for part in parts).casefold()

    @staticmethod
    def _candidate_matches(candidate: str, searchable_text: str) -> bool:
        normalized = candidate.casefold()
        return bool(normalized) and normalized in searchable_text

    @staticmethod
    def _next_role(decision: StepDecision) -> AgentRole | None:
        if decision.decision_type == StepDecisionType.PROPOSE_EXECUTION:
            return AgentRole.EXECUTOR
        if decision.decision_type == StepDecisionType.STEP_SUCCEEDED:
            return AgentRole.VERIFIER
        if decision.decision_type in {StepDecisionType.STEP_BLOCKED, StepDecisionType.REQUEST_REPLAN}:
            return AgentRole.RECOVERY
        return None


__all__ = ["StepPolicyAgent", "StepPolicyCallback"]
