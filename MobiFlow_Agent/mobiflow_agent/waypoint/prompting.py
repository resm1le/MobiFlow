from __future__ import annotations

from mobiflow_agent.intake.models import TestCase
from mobiflow_agent.model.prompting import PromptBundle

from .drafting import SequenceDraftRequest


class WaypointDraftPromptBuilder:
    def build(
        self,
        *,
        test_case: TestCase,
        request: SequenceDraftRequest,
        allowed_actions: list[str],
    ) -> PromptBundle:
        return PromptBundle(
            system_prompt=(
                "You decompose a parsed mobile test case into ordered semantic waypoint candidates. "
                "Every waypoint needs at least one observable arrival outcome; an action by itself is not "
                "arrival evidence. Use only the supplied allowed_actions. Do not invent accounts, contacts, "
                "products, devices, app packages, or facts absent from the source. Preserve a path_constraint "
                "only when the source states it explicitly. Do not emit device identity or rendezvous data. "
                "Do not write or format a catalog file. Return only a structured SequenceWaypointDraftCandidate."
            ),
            context_payload={
                "test_case": test_case.model_dump(mode="json"),
                "source_kind": request.source_kind.value,
                "sequence_metadata": {
                    "sequence_id": request.sequence_id,
                    "behavior_label": request.behavior_label,
                    "profile_package": request.profile_package,
                },
                "allowed_actions": list(allowed_actions),
            },
            preserve_keys=[
                "test_case",
                "source_kind",
                "sequence_metadata",
                "allowed_actions",
            ],
            metadata={"prompt_kind": "waypoint_draft_decomposer"},
        )


__all__ = ["WaypointDraftPromptBuilder"]
