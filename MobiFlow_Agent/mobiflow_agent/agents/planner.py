from __future__ import annotations

from typing import TYPE_CHECKING

from mobiflow_agent.agents.contracts import AgentRole, RoleRequest, RoleResult
from mobiflow_agent.common.contracts import (
    ApprovalMode,
    EntityKind,
    ExecutionProposal,
    StrictModel,
    SuccessCriterion,
    TaskContract,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.common.ids import (
    build_role_result_id,
    build_task_contract_id,
    build_task_plan_id,
    build_task_step_id,
)
from mobiflow_agent.model.prompting import PlannerPromptBuilder
from mobiflow_agent.model.runtime import ModelRuntime
from mobiflow_agent.task.plan import TaskPlan, TaskStep, TaskStepKind, TaskStepPolicy

if TYPE_CHECKING:
    from mobiflow_agent.task.session import TaskSession


class PlannerModelOutput(StrictModel):
    contract: TaskContract
    plan: TaskPlan


class PlannerAgent:
    DEFAULT_DYNAMIC_SIDE_EFFECTS = ["mobile.launch", "mobile.tap", "mobile.input_text", "mobile.wait", "mobile.back"]

    def __init__(
        self,
        *,
        model_client: ModelRuntime | None = None,
        prompt_builder: PlannerPromptBuilder | None = None,
    ):
        self._model_client = model_client
        self._prompt_builder = prompt_builder or PlannerPromptBuilder()

    def bind_model_runtime(self, model_client: ModelRuntime | None) -> None:
        if model_client is not None:
            self._model_client = model_client

    def plan(
        self,
        *,
        session_id: str,
        goal: str,
        target_kind: EntityKind | None = None,
        target_id: str | None = None,
        proposal: ExecutionProposal | None = None,
        verification_spec: VerificationSpec | None = None,
        request: RoleRequest | None = None,
        session: TaskSession | None = None,
    ) -> tuple[TaskContract, TaskPlan, RoleResult]:
        if request is not None and request.role != AgentRole.PLANNER:
            raise ValueError("PlannerAgent received a non-planner RoleRequest.")
        trace_refs: list[str] = []
        if self._model_client is not None and (session is None or session.active_model_profile is not None):
            prompt = self._prompt_builder.build(
                session=session,
                goal=goal,
                target_kind=target_kind.value if target_kind is not None else None,
                target_id=target_id,
                proposal=None if proposal is None else proposal.model_dump(mode="python"),
                verification_spec=(
                    None if verification_spec is None else verification_spec.model_dump(mode="python")
                ),
            )
            try:
                generated = self._model_client.generate_structured(
                    role=AgentRole.PLANNER,
                    prompt=prompt,
                    response_model=PlannerModelOutput,
                    profile_name=session.active_model_profile if session is not None else None,
                    metadata={"session_id": session_id},
                )
            except Exception as exc:
                raise ValueError("PlannerAgent model output failed validation.") from exc
            if session is not None:
                session.model_trace.append(generated.response.trace)
            trace_refs = [generated.response.trace.invocation_id]
            contract = generated.output.contract
            plan = generated.output.plan
        else:
            contract = self._build_contract(goal, target_kind, target_id)
            effective_spec = verification_spec or self._default_verification_spec(target_kind, target_id)
            plan = TaskPlan(
                plan_id=build_task_plan_id(),
                summary=f"Task control plan for: {goal}",
                steps=self._build_dynamic_steps(
                    goal=goal,
                    proposal=proposal,
                    target_kind=target_kind,
                    target_id=target_id,
                    verification_spec=effective_spec,
                ),
            )
        result = RoleResult(
            result_id=build_role_result_id(),
            role=AgentRole.PLANNER,
            session_id=session_id,
            step_id=plan.steps[0].step_id,
            summary="Planner agent produced the active task contract and multi-step plan.",
            payload={
                "contract": contract.model_dump(mode="python"),
                "plan": plan.model_dump(mode="python"),
                "model_trace_refs": trace_refs,
            },
            handoff_reason="plan_ready",
            next_role=AgentRole.OBSERVER,
        )
        return contract, plan, result

    @staticmethod
    def _build_contract(
        goal: str,
        target_kind: EntityKind | None,
        target_id: str | None,
    ) -> TaskContract:
        return TaskContract(
            contract_id=build_task_contract_id(),
            user_goal=goal,
            outcome=f"Advance task toward: {goal}",
            target_kind=target_kind,
            target_id=target_id,
            success_criteria=[
                SuccessCriterion(
                    criterion_id="primary-outcome",
                    description="Produce an evidence-backed verification verdict for the active task path.",
                    evidence_hint="verification verdict",
                )
            ],
            verification_focus=["evidence", "task-progress"],
            approval_mode=ApprovalMode.ON_RISK,
        )

    def _build_dynamic_steps(
        self,
        *,
        goal: str,
        proposal: ExecutionProposal | None,
        target_kind: EntityKind | None,
        target_id: str | None,
        verification_spec: VerificationSpec | None,
    ) -> list[TaskStep]:
        return [
            TaskStep(
                step_id=build_task_step_id(),
                kind=TaskStepKind.DYNAMIC,
                goal=f"Dynamically advance the task state for: {goal}",
                expected_outputs=["observation", "step_decision", "verification_verdict"],
                verification_target_kind=target_kind,
                verification_target_id=target_id,
                allowed_side_effects=[proposal.action_tool_name] if proposal is not None else self.DEFAULT_DYNAMIC_SIDE_EFFECTS,
                proposal=proposal,
                verification_spec=verification_spec,
                policy=TaskStepPolicy(
                    policy_id="dynamic-mobile-step-policy",
                    description="Observe the active target, choose bounded actions, and stop for verification.",
                    max_iterations=8,
                    action_hints=[proposal.action_tool_name] if proposal is not None else self.DEFAULT_DYNAMIC_SIDE_EFFECTS,
                ),
            )
        ]

    @staticmethod
    def _default_verification_spec(
        target_kind: EntityKind | None,
        target_id: str | None,
    ) -> VerificationSpec | None:
        if target_kind is None or target_id is None:
            return None
        return VerificationSpec(
            verification_id=f"verification:{target_kind.value}:{target_id}",
            target_kind=target_kind,
            target_id=target_id,
            success_checks=[
                VerificationCheck(
                    check_id="has-evidence",
                    description="The task concludes with evidence-backed verification.",
                    evidence_hint="observation evidence",
                )
            ],
        )
