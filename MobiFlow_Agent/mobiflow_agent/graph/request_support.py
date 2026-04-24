from __future__ import annotations

from mobiflow_agent.agents.contracts import AgentRole, RoleRequest, RoleResult
from mobiflow_agent.common.contracts import EntityKind
from mobiflow_agent.common.ids import build_role_request_id
from mobiflow_agent.task.session import TaskSession


class TaskGraphRequestSupportMixin:
    def _build_request(self, session: TaskSession, role: AgentRole, reason: str) -> RoleRequest:
        context_token_estimate = (
            session.session_digest.context_token_estimate
            if session.session_digest is not None
            else None
        )
        request = RoleRequest(
            request_id=build_role_request_id(),
            role=role,
            session_id=session.session_id,
            step_id=session.current_step.step_id if session.current_step else None,
            reason=reason,
            payload={
                "goal": session.goal,
                "status": session.status.value,
                "current_step_kind": session.current_step.kind.value if session.current_step else None,
                "current_step_index": session.current_step_index,
                "has_proposal": session.current_step.proposal is not None if session.current_step else False,
                "active_model_profile": session.active_model_profile,
                "context_compacted": session.session_digest is not None,
                "context_handoff_used": session.imported_handoff is not None,
                "context_token_estimate": context_token_estimate,
            },
        )
        session.role_requests.append(request)
        return request

    @staticmethod
    def _record_result(session: TaskSession, result: RoleResult, *, next_role: AgentRole | None) -> None:
        expected_step_id = session.current_step.step_id if session.current_step else None
        if result.session_id != session.session_id:
            raise ValueError("RoleResult session_id does not match the active TaskSession.")
        if result.step_id != expected_step_id:
            raise ValueError("RoleResult step_id does not match the active TaskSession step.")
        session.role_results.append(result.model_copy(update={"next_role": next_role}))

    @staticmethod
    def _focus(session: TaskSession) -> tuple[EntityKind, str]:
        if session.current_step and session.current_step.verification_target_kind and session.current_step.verification_target_id:
            return session.current_step.verification_target_kind, session.current_step.verification_target_id
        if session.target_kind and session.target_id:
            return session.target_kind, session.target_id
        return EntityKind.TASK, session.session_id


__all__ = ["TaskGraphRequestSupportMixin"]
