from __future__ import annotations

"""Recovery follow-up decision enum, kept free of any execution/graph dependency."""

from enum import Enum


class RecoveryFollowupDriverDecision(str, Enum):
    SCHEDULE_NEXT = "schedule_next"
    HANDOFF_ONLY = "handoff_only"
    COMPLETE = "complete"
    NO_FOLLOWUP = "no_followup"
