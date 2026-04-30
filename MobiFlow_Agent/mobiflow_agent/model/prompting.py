from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import Field

from mobiflow_agent.common.contracts import ObservationView, StrictModel, VerificationVerdict

if TYPE_CHECKING:
    from mobiflow_agent.task.session import TaskSession


class PromptBundle(StrictModel):
    system_prompt: str = Field(min_length=1)
    user_prompt: str = ""
    context_payload: dict[str, Any] = Field(default_factory=dict)
    preserve_keys: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class PlannerPromptBuilder:
    def build(
        self,
        *,
        session: TaskSession | None,
        goal: str,
        target_kind: str | None,
        target_id: str | None,
        proposal: dict[str, Any] | None,
        verification_spec: dict[str, Any] | None,
    ) -> PromptBundle:
        memory_context = (
            session.memory_context.get("planner", {})
            if session is not None
            else {}
        )
        return PromptBundle(
            system_prompt=(
                "You are the planner for a task-first agent. Produce only structured contract and plan output. "
                "Do not call tools. Keep side effects in execute steps only."
            ),
            user_prompt="",
            context_payload={
                "goal": goal,
                "target_kind": target_kind,
                "target_id": target_id,
                "proposal": proposal,
                "verification_spec": verification_spec,
                "memory_context": memory_context,
                "session_digest": (
                    session.session_digest.model_dump(mode="python")
                    if session is not None and session.session_digest is not None
                    else None
                ),
                "imported_handoff": (
                    session.imported_handoff.model_dump(mode="python")
                    if session is not None and session.imported_handoff is not None
                    else None
                ),
            },
            preserve_keys=["goal", "target_kind", "target_id", "proposal", "verification_spec"],
            metadata={"prompt_kind": "planner"},
        )


class RecoveryPromptBuilder:
    def build(
        self,
        *,
        session: TaskSession,
        failure_verdict: VerificationVerdict | None,
    ) -> PromptBundle:
        step_id = session.current_step.step_id if session.current_step is not None else "session"
        return PromptBundle(
            system_prompt=(
                "You are the recovery role for a task-first agent. Produce recovery guidance and a typed recovery "
                "outcome. Do not declare the task complete."
            ),
            user_prompt="",
            context_payload={
                "goal": session.goal,
                "target_kind": session.target_kind.value if session.target_kind is not None else None,
                "target_id": session.target_id,
                "failure_verdict": None if failure_verdict is None else failure_verdict.model_dump(mode="python"),
                "memory_context": session.memory_context.get(step_id, session.memory_context.get("recovery", {})),
                "recovery_guidance": (
                    session.recovery_guidance.model_dump(mode="python")
                    if session.recovery_guidance is not None
                    else None
                ),
                "last_observation_summary": (
                    _serialize(session.last_observation.model_dump(mode="python"))
                    if session.last_observation is not None
                    else None
                ),
                "session_digest": (
                    session.session_digest.model_dump(mode="python")
                    if session.session_digest is not None
                    else None
                ),
            },
            preserve_keys=["goal", "target_kind", "target_id", "failure_verdict"],
            metadata={"prompt_kind": "recovery"},
        )


class VerifierPromptBuilder:
    def build(
        self,
        *,
        session: TaskSession,
        observation: ObservationView | None,
    ) -> PromptBundle:
        step_id = session.current_step.step_id if session.current_step is not None else "session"
        return PromptBundle(
            system_prompt=(
                "You are the verifier for a task-first agent. Interpret evidence and checks, but do not claim success "
                "without evidence-backed support."
            ),
            user_prompt="",
            context_payload={
                "goal": session.goal,
                "active_verification_spec": (
                    session.active_verification_spec.model_dump(mode="python")
                    if session.active_verification_spec is not None
                    else None
                ),
                "observation": None if observation is None else observation.model_dump(mode="python"),
                "memory_context": session.memory_context.get(step_id, session.memory_context.get("verifier", {})),
                "evaluation_context": session.evaluation_context.get(step_id, {}),
                "recovery_outcome": (
                    session.recovery_outcome.model_dump(mode="python")
                    if session.recovery_outcome is not None
                    else None
                ),
                "session_digest": (
                    session.session_digest.model_dump(mode="python")
                    if session.session_digest is not None
                    else None
                ),
            },
            preserve_keys=["goal", "active_verification_spec", "observation"],
            metadata={"prompt_kind": "verifier"},
        )


class StepPolicyPromptBuilder:
    def build(self, *, session: TaskSession) -> PromptBundle:
        step = session.current_step
        step_id = step.step_id if step is not None else "session"
        return PromptBundle(
            system_prompt=(
                "You are the bounded step-policy role for a task-first mobile agent. "
                "Choose exactly one structured StepDecision. Do not propose side effects outside the current allowlist."
            ),
            user_prompt="",
            context_payload={
                "goal": session.goal,
                "current_step": None if step is None else step.model_dump(mode="python"),
                "allowed_side_effects": [] if step is None else list(step.allowed_side_effects),
                "last_observation": (
                    None if session.last_observation is None else session.last_observation.model_dump(mode="python")
                ),
                "last_execution_result": (
                    None
                    if session.last_execution_result is None
                    else session.last_execution_result.model_dump(mode="python")
                ),
                "last_verdict": None if session.last_verdict is None else session.last_verdict.model_dump(mode="python"),
                "recent_step_decisions": [
                    decision.model_dump(mode="python") for decision in session.step_decisions[-5:]
                ],
                "memory_context": session.memory_context.get(step_id, session.memory_context.get("step_policy", {})),
                "session_digest": (
                    session.session_digest.model_dump(mode="python")
                    if session.session_digest is not None
                    else None
                ),
            },
            preserve_keys=["goal", "current_step", "allowed_side_effects", "last_observation"],
            metadata={"prompt_kind": "step_policy"},
        )


__all__ = [
    "PlannerPromptBuilder",
    "PromptBundle",
    "RecoveryPromptBuilder",
    "StepPolicyPromptBuilder",
    "VerifierPromptBuilder",
]
