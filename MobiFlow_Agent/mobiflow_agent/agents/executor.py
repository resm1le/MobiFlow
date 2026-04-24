from __future__ import annotations

from mobiflow_agent.agents.contracts import AgentRole, RoleRequest, RoleResult
from mobiflow_agent.common.ids import build_role_result_id
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.runtime.state import CallerContext
from mobiflow_agent.task.session import TaskSession


class ExecutorAgent:
    def __init__(self, adapter: PlatformAdapter):
        self._adapter = adapter

    def execute(
        self,
        session: TaskSession,
        request: RoleRequest | None = None,
    ) -> tuple[GovernedActionResult, CallerContext, RoleResult]:
        if request is not None and request.role != AgentRole.EXECUTOR:
            raise ValueError("ExecutorAgent received a non-executor RoleRequest.")
        proposal = self._active_proposal(session)
        if session.current_step is None or proposal is None:
            raise ValueError("ExecutorAgent requires an active task step with a proposal.")
        caller_context = self._build_caller_context(session)
        result = self._adapter.submit_execution_proposal(proposal, caller_context)
        role_result = RoleResult(
            result_id=build_role_result_id(),
            role=AgentRole.EXECUTOR,
            session_id=session.session_id,
            step_id=session.current_step.step_id,
            summary=f"Executor agent submitted governed action {proposal.action_tool_name}.",
            payload={
                "execution_result": result.model_dump(mode="python"),
                "caller_context": caller_context.model_dump(mode="python"),
            },
            handoff_reason=result.state.value,
            next_role=AgentRole.OBSERVER if result.state != GovernedActionState.APPROVAL_REQUIRED else None,
        )
        return result, caller_context, role_result

    def resolve_approval(
        self,
        session: TaskSession,
        *,
        approved: bool,
        request: RoleRequest | None = None,
    ) -> tuple[GovernedActionResult, CallerContext, RoleResult]:
        if request is not None and request.role != AgentRole.EXECUTOR:
            raise ValueError("ExecutorAgent received a non-executor RoleRequest.")
        if session.pending_execution is None:
            raise ValueError("ExecutorAgent.resolve_approval requires pending execution on the active session.")
        if session.pending_execution.confirmation_id is None:
            raise ValueError("ExecutorAgent.resolve_approval requires a confirmation id.")
        caller_context = session.pending_execution.caller_context
        result = self._adapter.resolve_approval(
            session.pending_execution.confirmation_id,
            approved,
            caller_context,
        )
        role_result = RoleResult(
            result_id=build_role_result_id(),
            role=AgentRole.EXECUTOR,
            session_id=session.session_id,
            step_id=session.current_step.step_id if session.current_step else None,
            summary=f"Executor agent resolved approval for {session.pending_execution.proposal.action_tool_name}.",
            payload={
                "execution_result": result.model_dump(mode="python"),
                "caller_context": caller_context.model_dump(mode="python"),
                "approved": approved,
            },
            handoff_reason=f"approval_resolved:{result.state.value}",
            next_role=AgentRole.OBSERVER if result.state == GovernedActionState.EXECUTED else AgentRole.RECOVERY,
        )
        return result, caller_context, role_result

    @staticmethod
    def _build_caller_context(session: TaskSession) -> CallerContext:
        if session.current_step is None:
            raise ValueError("ExecutorAgent requires an active task step.")
        return CallerContext(
            session_id=session.session_id,
            agent_task_id=session.session_id,
            turn_id=str(len(session.status_history)),
            step_id=session.current_step.step_id,
        )

    @staticmethod
    def _active_proposal(session: TaskSession):
        if session.current_step is not None and session.current_step.proposal is not None:
            return session.current_step.proposal
        if session.last_step_decision is not None:
            return session.last_step_decision.proposal
        return None
