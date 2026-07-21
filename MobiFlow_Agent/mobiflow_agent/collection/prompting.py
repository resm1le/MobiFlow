from __future__ import annotations

from mobiflow_agent.collection.models import CollectionIntent
from mobiflow_agent.model.prompting import PromptBundle
from mobiflow_agent.platform.types import (
    DispatchDeviceContext,
    RunPlanningCatalogContext,
)
from mobiflow_agent.waypoint.catalog import SequenceSummary


class IntentPlannerPromptBuilder:
    def build(
        self,
        *,
        intent: CollectionIntent,
        sequences: list[SequenceSummary],
        devices: list[DispatchDeviceContext],
        planning_catalog: RunPlanningCatalogContext,
    ) -> PromptBundle:
        observed_tags = sorted({tag for device in devices for tag in device.tags})
        return PromptBundle(
            system_prompt=(
                "Map a constrained collection intent to one structured IntentPlannerDecision. "
                "Choose only complete versioned .vN sequence IDs supplied in sequence_catalog. "
                "Choose only device IDs in device_inventory and tags in observed_tags. Every dispatch "
                "selector must use exactly one form: device_ids, or count with required_tags and "
                "excluded_tags. Return CLARIFY when the sequence, count or device condition is missing, "
                "or when the meaning is ambiguous. Do not output sequence payloads, task payloads, run "
                "configuration, artifact policy, approval decisions, or device fields beyond selector "
                "identity. Do not call or include draft_sequence, do not create a new sequence, and do "
                "not infer an unlisted sequence, device, tag, profile, or task type."
            ),
            context_payload={
                "intent": intent.model_dump(mode="json"),
                "sequence_catalog": [
                    summary.model_dump(mode="json") for summary in sequences
                ],
                "device_inventory": [
                    device.model_dump(mode="json") for device in devices
                ],
                "observed_tags": observed_tags,
                "planning_catalog": {
                    "allowed_task_types": list(planning_catalog.allowed_task_types),
                    "available_profiles": [
                        profile.model_dump(mode="json")
                        for profile in planning_catalog.available_profiles
                    ],
                },
                "selector_contract": {
                    "explicit": {"device_ids": ["inventory device IDs"]},
                    "tagged": {
                        "count": "positive integer",
                        "required_tags": ["observed tags"],
                        "excluded_tags": ["observed tags"],
                    },
                    "exactly_one": True,
                },
            },
            preserve_keys=[
                "intent",
                "sequence_catalog",
                "device_inventory",
                "observed_tags",
                "planning_catalog",
                "selector_contract",
            ],
            metadata={"prompt_kind": "collection_intent_planner"},
        )


__all__ = ["IntentPlannerPromptBuilder"]
