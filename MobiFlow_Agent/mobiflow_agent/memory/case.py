from __future__ import annotations

"""Recovery memory case assets and retrieval service."""

from enum import Enum
from uuid import uuid4

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel, VerificationStatus
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from mobiflow_agent.evaluation.replay import RecoveryEvalCase, RecoveryReplayCase
from mobiflow_agent.memory.models import TaskMemoryRecord, TaskMemoryRecordKind
from mobiflow_agent.runtime.harness import TaskHarnessResponse
from mobiflow_agent.task.plan import TaskStepKind

class MemoryCaseSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryMemoryCase(StrictModel):
    schema_version: MemoryCaseSchemaVersion = MemoryCaseSchemaVersion.V1
    case_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    category: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    decision: RecoveryFollowupDriverDecision
    verdict_status: VerificationStatus | None = None
    input_summary: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    replay_case: RecoveryReplayCase
    eval_case: RecoveryEvalCase | None = None

class RecoveryCaseQuery(StrictModel):
    schema_version: MemoryCaseSchemaVersion = MemoryCaseSchemaVersion.V1
    category: str | None = None
    action_name: str | None = None
    decision: RecoveryFollowupDriverDecision | None = None
    verdict_status: VerificationStatus | None = None
    tags: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1)

class RecoveryCaseMatch(StrictModel):
    case: RecoveryMemoryCase
    score: int = Field(ge=0)
    summary: str = Field(min_length=1)

class RecoveryCaseRetrievalResponse(StrictModel):
    schema_version: MemoryCaseSchemaVersion = MemoryCaseSchemaVersion.V1
    query: RecoveryCaseQuery
    matches: list[RecoveryCaseMatch] = Field(default_factory=list)
    summary: str = Field(min_length=1)

def build_memory_case_id() -> str:
    return f"memory:{uuid4().hex}"

class MemoryCaseRetrievalService:
    def build_case(
        self,
        *,
        source: str,
        replay_case: RecoveryReplayCase,
        eval_case: RecoveryEvalCase | None = None,
        category: str,
        input_summary: str,
        tags: list[str] | None = None,
    ) -> RecoveryMemoryCase:
        return RecoveryMemoryCase(
            case_id=build_memory_case_id(),
            source=source,
            category=category,
            action_name=replay_case.execution.action_name,
            decision=replay_case.harness_response.decision,
            verdict_status=self._extract_verdict_status(replay_case.harness_response),
            input_summary=input_summary,
            tags=self._normalize_tags(tags),
            replay_case=replay_case,
            eval_case=eval_case,
        )

    def retrieve(
        self,
        *,
        query: RecoveryCaseQuery,
        cases: list[RecoveryMemoryCase],
    ) -> RecoveryCaseRetrievalResponse:
        if self._is_empty_query(query):
            return RecoveryCaseRetrievalResponse(
                query=query,
                matches=[],
                summary="Recovery case retrieval requires at least one query filter.",
            )

        scored_matches: list[RecoveryCaseMatch] = []
        query_tags = self._normalize_tags(query.tags)
        for case in cases:
            score = 0
            matched_fields: list[str] = []

            if query.action_name is not None and case.action_name == query.action_name:
                score += 4
                matched_fields.append(f"action_name={case.action_name}")
            if query.category is not None and case.category == query.category:
                score += 3
                matched_fields.append(f"category={case.category}")
            if query.verdict_status is not None and case.verdict_status == query.verdict_status:
                score += 2
                matched_fields.append(f"verdict_status={query.verdict_status.value}")
            if query.decision is not None and case.decision == query.decision:
                score += 2
                matched_fields.append(f"decision={query.decision.value}")

            tag_matches = [tag for tag in query_tags if tag in case.tags]
            if tag_matches:
                score += len(tag_matches)
                matched_fields.extend(f"tag={tag}" for tag in tag_matches)

            if score > 0:
                summary = "Matched on " + ", ".join(matched_fields) + f" (score={score})."
                scored_matches.append(
                    RecoveryCaseMatch(
                        case=case,
                        score=score,
                        summary=summary,
                    )
                )

        ordered_matches = sorted(
            scored_matches,
            key=lambda match: (-match.score, match.case.case_id),
        )
        limited_matches = ordered_matches[: query.limit]
        summary = (
            f"Retrieved {len(limited_matches)} recovery memory case(s)."
            if limited_matches
            else "No recovery memory cases matched the query."
        )
        return RecoveryCaseRetrievalResponse(
            query=query,
            matches=limited_matches,
            summary=summary,
        )

    @staticmethod
    def _extract_verdict_status(
        harness_response: TaskHarnessResponse,
    ) -> VerificationStatus | None:
        if harness_response.latest_verdict is None:
            return None
        return harness_response.latest_verdict.status

    @staticmethod
    def _is_empty_query(query: RecoveryCaseQuery) -> bool:
        return not any(
            (
                query.category,
                query.action_name,
                query.decision,
                query.verdict_status,
                query.tags,
            )
        )

    @staticmethod
    def _normalize_tags(tags: list[str] | None) -> list[str]:
        if not tags:
            return []
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tag in tags:
            tag = raw_tag.strip()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            normalized.append(tag)
        return normalized


def recovery_case_to_task_memory_record(case: RecoveryMemoryCase) -> TaskMemoryRecord:
    latest_verdict = case.replay_case.harness_response.latest_verdict
    return TaskMemoryRecord(
        memory_id=f"legacy-{case.case_id}",
        kind=TaskMemoryRecordKind.RECOVERY_PATTERN,
        source=case.source,
        goal=case.input_summary,
        target_kind=latest_verdict.target_kind if latest_verdict is not None else None,
        target_id=latest_verdict.target_id if latest_verdict is not None else None,
        step_kind=TaskStepKind.RECOVER,
        role_scope="recovery",
        verdict_status=case.verdict_status,
        blocked_reason=latest_verdict.blocked_reason if latest_verdict is not None else None,
        summary=case.input_summary,
        tags=list(case.tags),
        evidence_ref_ids=(
            [ref.evidence_id for ref in latest_verdict.evidence_refs]
            if latest_verdict is not None
            else []
        ),
        proposal_fingerprint=case.action_name,
        content_payload={
            "category": case.category,
            "action_name": case.action_name,
            "decision": case.decision.value,
            "replay_case_id": case.replay_case.case_id,
        },
        created_at_ms=0,
        updated_at_ms=0,
    )
