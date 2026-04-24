from __future__ import annotations

from typing import Callable

from mobiflow_agent.agents.contracts import AgentRole, RoleRequest, RoleResult
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
)
from mobiflow_agent.common.ids import build_role_result_id
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.task.plan import TaskStatus
from mobiflow_agent.task.session import TaskSession


ObservationProvider = Callable[[TaskSession], ObservationView]


class ObserverAgent:
    def __init__(
        self,
        adapter: PlatformAdapter | None = None,
        *,
        observation_provider: ObservationProvider | None = None,
    ):
        self._adapter = adapter
        self._observation_provider = observation_provider

    def observe(self, session: TaskSession, request: RoleRequest | None = None) -> tuple[ObservationView, RoleResult]:
        if request is not None and request.role != AgentRole.OBSERVER:
            raise ValueError("ObserverAgent received a non-observer RoleRequest.")
        observation = self._build_observation(session)
        next_role = AgentRole.VERIFIER
        if session.current_step and session.current_step.proposal is not None:
            previous_status = session.status_history[-2] if len(session.status_history) >= 2 else None
            next_role = AgentRole.VERIFIER if previous_status == TaskStatus.EXECUTING else AgentRole.EXECUTOR
        result = RoleResult(
            result_id=build_role_result_id(),
            role=AgentRole.OBSERVER,
            session_id=session.session_id,
            step_id=session.current_step.step_id if session.current_step else None,
            summary="Observer agent produced the latest canonical observation.",
            payload={"observation": observation.model_dump(mode="python")},
            handoff_reason="observation_ready",
            next_role=next_role,
        )
        return observation, result

    def _build_observation(self, session: TaskSession) -> ObservationView:
        if self._observation_provider is not None:
            return self._observation_provider(session)
        if session.current_step is not None:
            if (
                self._adapter is not None
                and session.current_step.verification_target_kind is not None
                and session.current_step.verification_target_id is not None
            ):
                return self._adapter.observe_target(
                    session.current_step.verification_target_kind,
                    session.current_step.verification_target_id,
                )
        evidence = EvidenceRef(
            evidence_id=f"observation-note:{session.session_id}",
            kind=EvidenceKind.INLINE_NOTE,
            summary="No platform adapter was configured; using a minimal agent observation.",
            locator=session.session_id,
        )
        return ObservationView(
            observation_id=f"observation:{session.session_id}",
            focus_kind=session.current_step.verification_target_kind if session.current_step and session.current_step.verification_target_kind else EntityKind.TASK,
            focus_id=session.current_step.verification_target_id if session.current_step and session.current_step.verification_target_id else session.session_id,
            facts=[
                ObservationFact(
                    fact_id="agent_fallback_observation",
                    source=ObservationFactSource.AGENT,
                    title="Agent fallback observation",
                    value={"session_id": session.session_id, "goal": session.goal},
                    evidence_refs=[evidence],
                )
            ],
            inferences=[],
            resource_handles=[],
        )
