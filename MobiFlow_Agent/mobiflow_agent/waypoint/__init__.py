from importlib import import_module

from mobiflow_agent.waypoint.catalog import (
    SEQUENCE_ID_PATTERN,
    SequenceCatalog,
    SequenceCatalogError,
    SequenceSummary,
)
from mobiflow_agent.waypoint.compiler import compile_sequence_to_plan
from mobiflow_agent.waypoint.models import (
    PathConstraint,
    RendezvousSpec,
    Waypoint,
    WaypointSequence,
    WaypointStrength,
)

__all__ = [
    "PathConstraint",
    "RendezvousSpec",
    "SEQUENCE_ID_PATTERN",
    "SequenceCatalog",
    "SequenceCatalogError",
    "SequenceSummary",
    "DraftWaypointCandidate",
    "SequenceDraftRequest",
    "SequenceDraftResult",
    "SequenceDraftSourceKind",
    "SequenceWaypointDraftCandidate",
    "Waypoint",
    "WaypointSequence",
    "WaypointStrength",
    "WaypointDecompositionResult",
    "WaypointDraftDecomposer",
    "compile_sequence_to_plan",
]


def __getattr__(name: str):
    if name in {
        "DraftWaypointCandidate",
        "SequenceDraftRequest",
        "SequenceDraftResult",
        "SequenceDraftSourceKind",
        "SequenceWaypointDraftCandidate",
        "WaypointDecompositionResult",
        "WaypointDraftDecomposer",
    }:
        module = import_module("mobiflow_agent.waypoint.drafting")
        return getattr(module, name)
    raise AttributeError(f"module 'mobiflow_agent.waypoint' has no attribute {name!r}")
