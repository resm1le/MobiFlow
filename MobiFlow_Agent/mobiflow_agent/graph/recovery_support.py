from __future__ import annotations

from mobiflow_agent.agents.contracts import RecoveryOutcome
from mobiflow_agent.common.contracts import (
    EvidenceKind,
    EvidenceRef,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
)
from mobiflow_agent.task.session import TaskSession


class TaskGraphRecoverySupportMixin:
    def _build_recovery_observation(
        self,
        session: TaskSession,
        recovery_outcome: RecoveryOutcome,
    ) -> ObservationView | None:
        if recovery_outcome.observation is None and not recovery_outcome.evidence_refs:
            return None
        target_kind, target_id = self._focus(session)
        return ObservationView(
            observation_id=f"recovery-observation:{session.session_id}",
            focus_kind=target_kind,
            focus_id=target_id,
            facts=[
                ObservationFact(
                    fact_id=f"recovery-fact:{session.session_id}",
                    source=ObservationFactSource.AGENT,
                    title="Recovery outcome",
                    value={
                        "summary": recovery_outcome.summary,
                        "has_guidance": recovery_outcome.guidance is not None,
                        "has_execution_context": recovery_outcome.execution_context is not None,
                        "has_observation": recovery_outcome.observation is not None,
                    },
                    evidence_refs=recovery_outcome.evidence_refs
                    or [
                        EvidenceRef(
                            evidence_id=f"recovery-note:{session.session_id}",
                            kind=EvidenceKind.INLINE_NOTE,
                            summary=recovery_outcome.summary,
                            locator=target_id,
                        )
                    ],
                )
            ],
            resource_handles=[],
        )


__all__ = ["TaskGraphRecoverySupportMixin"]
