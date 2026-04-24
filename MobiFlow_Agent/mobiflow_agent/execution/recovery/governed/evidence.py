from __future__ import annotations

from mobiflow_agent.common.contracts import EvidenceRef
from mobiflow_agent.execution.recovery.common import (
    inline_note_evidence,
    result_evidence,
    result_evidence_from_state,
    snapshot_evidence,
    verification_check_ids,
)

EMPTY_GOVERNED_RECOVERY_EVIDENCE = (
    "Pending governed recovery action {action_tool_name} has no platform evidence attached yet."
)

__all__ = [
    "EMPTY_GOVERNED_RECOVERY_EVIDENCE",
    "EvidenceRef",
    "inline_note_evidence",
    "result_evidence",
    "result_evidence_from_state",
    "snapshot_evidence",
    "verification_check_ids",
]
