from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.memory.models import (
    TaskMemoryContext,
    TaskMemoryPolicy,
    TaskMemoryQuery,
    TaskMemoryRecord,
    TaskMemoryRecordKind,
    TaskMemoryWritebackRequest,
    TaskMemoryWritebackResult,
)
from mobiflow_agent.memory.governance import (
    TaskMemoryGovernanceDecision,
    TaskMemoryGovernanceService,
)
from mobiflow_agent.memory.quality import TaskMemoryQualityService
from mobiflow_agent.memory.retrieval import TaskMemoryRetrievalService
from mobiflow_agent.memory.store import TaskMemoryStore, build_memory_timestamp_ms
from mobiflow_agent.model.runtime import ModelRuntime
from mobiflow_agent.runtime.context import ContextCompressionService
from mobiflow_agent.task.plan import TaskStepKind
from mobiflow_agent.task.session import TaskSession


class TaskMemoryRuntime:
    def __init__(
        self,
        *,
        store: TaskMemoryStore,
        model_runtime: ModelRuntime | None = None,
        embedding_profile_name: str | None = None,
        policy: TaskMemoryPolicy | None = None,
        context_compressor: ContextCompressionService | None = None,
        quality_service: TaskMemoryQualityService | None = None,
        governance_service: TaskMemoryGovernanceService | None = None,
    ) -> None:
        self._store = store
        self._model_runtime = model_runtime
        self._embedding_profile_name = embedding_profile_name
        self._policy = policy or TaskMemoryPolicy()
        self._context_compressor = context_compressor or ContextCompressionService()
        self._retrieval_service = TaskMemoryRetrievalService(store=store, policy=self._policy)
        self._quality_service = quality_service or TaskMemoryQualityService()
        self._governance_service = governance_service or TaskMemoryGovernanceService()
        self._retrieval_contexts: list[TaskMemoryContext] = []
        self._writeback_results: list[TaskMemoryWritebackResult] = []

    @property
    def embedding_profile_name(self) -> str | None:
        return self._embedding_profile_name

    def list_records(self) -> list[TaskMemoryRecord]:
        return self._store.list_records()

    def retrieval_contexts(self) -> list[TaskMemoryContext]:
        return [context.model_copy(deep=True) for context in self._retrieval_contexts]

    def writeback_results(self) -> list[TaskMemoryWritebackResult]:
        return [result.model_copy(deep=True) for result in self._writeback_results]

    def bind_model_runtime(self, model_runtime: ModelRuntime | None) -> None:
        if model_runtime is not None:
            self._model_runtime = model_runtime

    def prepare_context(self, session: TaskSession, *, role: AgentRole) -> TaskMemoryContext:
        self._governance_service.expire_due_records(self._store)
        query = self._build_query(session, role=role)
        query_vector = self.embed_query(query.semantic_query_text)
        candidate_records = self._store.query_records(query)
        self.ensure_record_embeddings(candidate_records)
        if query_vector is not None and self._embedding_profile_name is not None:
            retrieval = self._retrieval_service.hybrid_retrieve(
                query,
                query_vector=query_vector,
                profile_name=self._embedding_profile_name,
            )
        else:
            retrieval = self._retrieval_service.deterministic_retrieve(query)
        highlights = [
            self._highlight_for_match(match)
            for match in retrieval.matches[: self._policy.max_highlights]
        ]
        for match in retrieval.matches:
            self._store.touch_record(match.record.memory_id)
        context = TaskMemoryContext(
            role_scope=role.value,
            query=query,
            channel=retrieval.channel,
            matches=retrieval.matches,
            highlights=highlights,
            summary=retrieval.summary,
            retrieval_token_estimate=self._context_compressor.estimate_tokens(highlights),
        )
        self._retrieval_contexts.append(context)
        return context

    def writeback_session(self, session: TaskSession) -> TaskMemoryWritebackResult:
        if not self._policy.writeback_enabled:
            result = TaskMemoryWritebackResult(
                session_id=session.session_id,
                summary="Task memory writeback is disabled by policy.",
            )
            self._writeback_results.append(result)
            return result
        if session.last_verdict is None:
            result = TaskMemoryWritebackResult(
                session_id=session.session_id,
                summary="Task memory writeback skipped because the session does not have a verdict.",
            )
            self._writeback_results.append(result)
            return result
        records = self._candidate_writeback_records(session)
        stored: list[TaskMemoryRecord] = []
        rejected: list[TaskMemoryRecord] = []
        skipped: list[TaskMemoryRecordKind] = []
        quality_issue_summaries: list[str] = []
        governance_issue_summaries: list[str] = []
        created_count = 0
        updated_count = 0
        quarantined_count = 0
        superseded_count = 0
        expired_count = 0
        stored_active_records: list[TaskMemoryRecord] = []
        for record in records:
            if record.kind not in self._policy.writeback_kinds:
                skipped.append(record.kind)
                continue
            compacted_record = self._compact_record(record)
            assessment = self._quality_service.assess_record(compacted_record, policy=self._policy)
            quality_issue_summaries.extend(issue.summary for issue in assessment.issues)
            existing = self._store.get_record(compacted_record.memory_id)
            governance = self._governance_service.govern_record(
                compacted_record,
                quality_assessment=assessment,
                existing_record=existing,
            )
            governance_issue_summaries.extend(issue.summary for issue in governance.issues)
            if governance.decision == TaskMemoryGovernanceDecision.REJECTED or governance.record is None:
                rejected.append(compacted_record)
                continue

            record_to_store = governance.record
            if existing is None:
                created_count += 1
            else:
                updated_count += 1
            if governance.decision == TaskMemoryGovernanceDecision.QUARANTINED:
                quarantined_count += 1
            self._store.put_record(record_to_store)
            stored.append(record_to_store)
            if governance.decision in {
                TaskMemoryGovernanceDecision.ACTIVE,
                TaskMemoryGovernanceDecision.UPDATED,
            }:
                stored_active_records.append(record_to_store)
                if record_to_store.proposal_fingerprint is not None:
                    governance_report = self._governance_service.supersede_excess_versions(
                        self._store,
                        proposal_fingerprint=record_to_store.proposal_fingerprint,
                        keep_memory_id=record_to_store.memory_id,
                    )
                    superseded_count += governance_report.superseded_count
                    governance_issue_summaries.extend(issue.summary for issue in governance_report.issues)
        self.ensure_record_embeddings(stored_active_records)
        expiry_report = self._governance_service.expire_due_records(self._store)
        expired_count += expiry_report.expired_count
        governance_issue_summaries.extend(issue.summary for issue in expiry_report.issues)
        result = TaskMemoryWritebackResult(
            session_id=session.session_id,
            stored_records=stored,
            rejected_records=rejected,
            skipped_record_kinds=skipped,
            created_count=created_count,
            updated_count=updated_count,
            rejected_count=len(rejected),
            quarantined_count=quarantined_count,
            superseded_count=superseded_count,
            expired_count=expired_count,
            quality_issue_summaries=quality_issue_summaries,
            governance_issue_summaries=governance_issue_summaries,
            summary=(
                f"Task memory writeback for session {session.session_id}: "
                f"created={created_count}, updated={updated_count}, rejected={len(rejected)}, "
                f"quarantined={quarantined_count}, superseded={superseded_count}, "
                f"expired={expired_count}, skipped={len(skipped)}."
            ),
        )
        self._writeback_results.append(result)
        return result

    def build_writeback_request(self, session: TaskSession) -> TaskMemoryWritebackRequest:
        return TaskMemoryWritebackRequest(
            session_id=session.session_id,
            goal=session.goal,
            source="orchestrator.verify",
            records=self._build_records(session),
        )

    def embed_query(self, text: str | None) -> list[float] | None:
        if not text or self._model_runtime is None or self._embedding_profile_name is None:
            return None
        try:
            return self._model_runtime.embed_text(
                text,
                profile_name=self._embedding_profile_name,
                metadata={"subsystem": "memory_query"},
            )
        except Exception:
            return None

    def ensure_record_embeddings(self, records: list[TaskMemoryRecord]) -> None:
        if not records or self._model_runtime is None or self._embedding_profile_name is None:
            return
        self._retrieval_service.ensure_embeddings(
            records,
            profile_name=self._embedding_profile_name,
            embedder=lambda text: self._model_runtime.embed_text(
                text,
                profile_name=self._embedding_profile_name,
                metadata={"subsystem": "memory"},
            ),
            render_text=self._render_embedding_text,
        )

    def _build_query(self, session: TaskSession, *, role: AgentRole) -> TaskMemoryQuery:
        top_k = self._top_k_for_role(role)
        kinds = self._kinds_for_role(role)
        blocked_reason = session.last_verdict.blocked_reason if session.last_verdict is not None else None
        semantic_query_text = " ".join(
            part
            for part in [
                session.goal,
                blocked_reason,
                session.current_step.goal if session.current_step is not None else None,
                session.last_verdict.summary if session.last_verdict is not None else None,
            ]
            if part
        )
        return TaskMemoryQuery(
            role_scope=role.value,
            step_kind=self._query_step_kind(session, role=role),
            kinds=kinds,
            goal_text=session.goal,
            target_kind=session.target_kind,
            target_id=session.target_id,
            verdict_statuses=(
                [session.last_verdict.status]
                if role == AgentRole.RECOVERY and session.last_verdict is not None
                else []
            ),
            blocked_reason=blocked_reason if role in {AgentRole.RECOVERY, AgentRole.VERIFIER} else None,
            tags=self._query_tags(session, role=role),
            top_k=top_k,
            semantic_query_text=semantic_query_text or None,
            min_score=self._policy.min_score,
        )

    def _build_records(self, session: TaskSession) -> list[TaskMemoryRecord]:
        now_ms = build_memory_timestamp_ms()
        evidence_ref_ids = self._evidence_ref_ids(session)
        tags = self._record_tags(session)
        base_payload = {
            "session_id": session.session_id,
            "status": session.status.value,
            "completion_verdict": (
                session.completion_verdict.value if session.completion_verdict is not None else None
            ),
            "last_verdict_summary": session.last_verdict.summary if session.last_verdict is not None else None,
            "last_observation_id": (
                session.last_observation.observation_id if session.last_observation is not None else None
            ),
            "active_verification_id": (
                session.active_verification_spec.verification_id
                if session.active_verification_spec is not None
                else None
            ),
            "audit_id": (
                session.last_execution_result.audit.audit_id
                if session.last_execution_result is not None
                and session.last_execution_result.audit is not None
                else None
            ),
        }
        records: list[TaskMemoryRecord] = []
        if session.plan is not None and session.last_verdict is not None and session.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS:
            records.append(
                self._build_record(
                    session,
                    kind=TaskMemoryRecordKind.PLANNING_PATTERN,
                    role_scope=AgentRole.PLANNER.value,
                    summary=f"Planning pattern for goal '{session.goal}' completed with evidence-backed success.",
                    tags=tags + [AgentRole.PLANNER.value],
                    evidence_ref_ids=evidence_ref_ids,
                    payload={
                        **base_payload,
                        "plan_summary": session.plan.summary,
                        "step_count": len(session.plan.steps),
                    },
                    created_at_ms=now_ms,
                )
            )
        if session.last_verdict is not None:
            records.append(
                self._build_record(
                    session,
                    kind=TaskMemoryRecordKind.VERIFICATION_PATTERN,
                    role_scope=AgentRole.VERIFIER.value,
                    summary=session.last_verdict.summary,
                    tags=tags + [AgentRole.VERIFIER.value],
                    evidence_ref_ids=evidence_ref_ids,
                    payload={
                        **base_payload,
                        "matched_check_ids": list(session.last_verdict.matched_check_ids),
                        "unmatched_check_ids": list(session.last_verdict.unmatched_check_ids),
                        "blocked_reason": session.last_verdict.blocked_reason,
                    },
                    created_at_ms=now_ms,
                )
            )
        if session.recovery_outcome is not None:
            records.append(
                self._build_record(
                    session,
                    kind=TaskMemoryRecordKind.RECOVERY_PATTERN,
                    role_scope=AgentRole.RECOVERY.value,
                    summary=session.recovery_outcome.summary,
                    tags=tags + [AgentRole.RECOVERY.value, "recovery"],
                    evidence_ref_ids=evidence_ref_ids,
                    payload={
                        **base_payload,
                        "recovery_guidance": (
                            session.recovery_outcome.guidance.model_dump(mode="python")
                            if session.recovery_outcome.guidance is not None
                            else None
                        ),
                        "has_execution_context": session.recovery_outcome.execution_context is not None,
                    },
                    created_at_ms=now_ms,
                )
            )
        if session.last_verdict is not None:
            records.append(
                self._build_record(
                    session,
                    kind=TaskMemoryRecordKind.TASK_OUTCOME,
                    role_scope=AgentRole.PLANNER.value,
                    summary=f"Task outcome for goal '{session.goal}': {session.last_verdict.summary}",
                    tags=tags + [AgentRole.PLANNER.value, "task_outcome"],
                    evidence_ref_ids=evidence_ref_ids,
                    payload=base_payload,
                    created_at_ms=now_ms,
                )
            )
        return records

    def _candidate_writeback_records(self, session: TaskSession) -> list[TaskMemoryRecord]:
        return self._build_records(session)[: self._policy.max_records_per_session]

    def _build_record(
        self,
        session: TaskSession,
        *,
        kind: TaskMemoryRecordKind,
        role_scope: str,
        summary: str,
        tags: list[str],
        evidence_ref_ids: list[str],
        payload: dict[str, Any],
        created_at_ms: int,
    ) -> TaskMemoryRecord:
        proposal_fingerprint = self._proposal_fingerprint(session)
        fingerprint = self._fingerprint(
            goal=session.goal,
            kind=kind.value,
            role_scope=role_scope,
            summary=summary,
            blocked_reason=session.last_verdict.blocked_reason if session.last_verdict is not None else None,
            proposal_fingerprint=proposal_fingerprint,
        )
        return TaskMemoryRecord(
            memory_id=f"task-memory:{fingerprint}",
            kind=kind,
            source="task_orchestrator",
            goal=session.goal,
            target_kind=session.target_kind,
            target_id=session.target_id,
            step_kind=session.current_step.kind if session.current_step is not None else None,
            role_scope=role_scope,
            verdict_status=session.last_verdict.status if session.last_verdict is not None else None,
            blocked_reason=session.last_verdict.blocked_reason if session.last_verdict is not None else None,
            summary=summary,
            tags=self._normalized_tags(tags),
            evidence_ref_ids=evidence_ref_ids,
            proposal_fingerprint=proposal_fingerprint,
            content_payload=payload,
            created_at_ms=created_at_ms,
            updated_at_ms=created_at_ms,
        )

    def _ensure_embeddings(self, records: list[TaskMemoryRecord]) -> None:
        self.ensure_record_embeddings(records)

    def _embed_query(self, text: str | None) -> list[float] | None:
        return self.embed_query(text)

    def _compact_record(self, record: TaskMemoryRecord) -> TaskMemoryRecord:
        compacted_payload = self._compact_payload(record.content_payload, max_chars=self._policy.max_payload_chars)
        return record.model_copy(update={"content_payload": compacted_payload})

    def _compact_payload(self, payload: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
        blocked_keys = {
            "raw_prompt",
            "prompt",
            "provider_response",
            "model_response",
            "session_dump",
            "observation",
            "full_observation",
        }
        compacted = {
            key: self._compact_value(value)
            for key, value in payload.items()
            if key not in blocked_keys
        }
        while len(json.dumps(compacted, ensure_ascii=False, default=str)) > max_chars and compacted:
            removable_keys = [
                key
                for key in compacted
                if key
                not in {
                    "session_id",
                    "status",
                    "completion_verdict",
                    "last_verdict_summary",
                    "matched_check_ids",
                    "unmatched_check_ids",
                    "blocked_reason",
                    "recovery_guidance",
                }
            ]
            if not removable_keys:
                break
            compacted.pop(removable_keys[-1], None)
        return compacted

    def _compact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return value if len(value) <= 500 else value[:497] + "..."
        if isinstance(value, list):
            return [self._compact_value(item) for item in value[:20]]
        if isinstance(value, dict):
            return {key: self._compact_value(item) for key, item in list(value.items())[:30]}
        return value

    def _render_embedding_text(self, record: TaskMemoryRecord) -> str:
        parts = [
            f"kind: {record.kind.value}",
            f"goal: {record.goal}",
            f"summary: {record.summary}",
            f"role_scope: {record.role_scope or 'none'}",
            f"step_kind: {record.step_kind.value if record.step_kind is not None else 'none'}",
            f"blocked_reason: {record.blocked_reason or 'none'}",
            f"tags: {', '.join(record.tags) if record.tags else '(none)'}",
        ]
        return "\n".join(parts)

    def _highlight_for_match(self, match) -> dict[str, Any]:
        return {
            "memory_id": match.record.memory_id,
            "kind": match.record.kind.value,
            "summary": match.record.summary,
            "score": round(match.score, 4),
            "tags": match.record.tags,
            "blocked_reason": match.record.blocked_reason,
            "evidence_ref_ids": match.record.evidence_ref_ids[:5],
        }

    def _top_k_for_role(self, role: AgentRole) -> int:
        if role == AgentRole.PLANNER:
            return self._policy.planner_top_k
        if role == AgentRole.RECOVERY:
            return self._policy.recovery_top_k
        return self._policy.verifier_top_k

    @staticmethod
    def _query_step_kind(session: TaskSession, *, role: AgentRole):
        if role == AgentRole.PLANNER:
            return None
        if role == AgentRole.RECOVERY:
            return TaskStepKind.RECOVER
        if role == AgentRole.VERIFIER:
            return TaskStepKind.VERIFY
        return session.current_step.kind if session.current_step is not None else None

    @staticmethod
    def _kinds_for_role(role: AgentRole) -> list[TaskMemoryRecordKind]:
        if role == AgentRole.PLANNER:
            return [
                TaskMemoryRecordKind.PLANNING_PATTERN,
                TaskMemoryRecordKind.TASK_OUTCOME,
                TaskMemoryRecordKind.SCENARIO_OUTCOME,
            ]
        if role == AgentRole.RECOVERY:
            return [
                TaskMemoryRecordKind.RECOVERY_PATTERN,
                TaskMemoryRecordKind.TASK_OUTCOME,
                TaskMemoryRecordKind.VERIFICATION_PATTERN,
            ]
        return [
            TaskMemoryRecordKind.VERIFICATION_PATTERN,
            TaskMemoryRecordKind.RECOVERY_PATTERN,
            TaskMemoryRecordKind.TASK_OUTCOME,
        ]

    @staticmethod
    def _query_tags(session: TaskSession, *, role: AgentRole) -> list[str]:
        tags = [role.value]
        if session.current_step is not None:
            tags.append(session.current_step.kind.value)
        if session.last_verdict is not None:
            tags.append(session.last_verdict.status.value)
            if session.last_verdict.blocked_reason is not None:
                tags.append(session.last_verdict.blocked_reason)
        return TaskMemoryRuntime._normalized_tags(tags)

    @staticmethod
    def _record_tags(session: TaskSession) -> list[str]:
        tags = []
        if session.current_step is not None:
            tags.append(session.current_step.kind.value)
        if session.last_verdict is not None:
            tags.append(session.last_verdict.status.value)
            if session.last_verdict.blocked_reason is not None:
                tags.append(session.last_verdict.blocked_reason)
        if session.recovery_outcome is not None:
            tags.append("recovery")
        return TaskMemoryRuntime._normalized_tags(tags)

    @staticmethod
    def _proposal_fingerprint(session: TaskSession) -> str | None:
        proposal = None
        if session.current_step is not None:
            proposal = session.current_step.proposal
        if proposal is None:
            proposal = session.initial_proposal
        if proposal is not None:
            payload = {
                "tool": proposal.action_tool_name,
                "target_kind": proposal.target_kind.value if proposal.target_kind is not None else None,
                "target_id": proposal.target_id,
                "arguments": proposal.arguments,
            }
        else:
            payload = {
                "goal": session.goal,
                "target_kind": session.target_kind.value if session.target_kind is not None else None,
                "target_id": session.target_id,
                "verification_id": (
                    session.active_verification_spec.verification_id
                    if session.active_verification_spec is not None
                    else None
                ),
            }
        return sha256(str(payload).encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _fingerprint(
        *,
        goal: str,
        kind: str,
        role_scope: str,
        summary: str,
        blocked_reason: str | None,
        proposal_fingerprint: str | None,
    ) -> str:
        payload = "|".join(
            [
                goal,
                kind,
                role_scope,
                summary,
                blocked_reason or "",
                proposal_fingerprint or "",
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _evidence_ref_ids(session: TaskSession) -> list[str]:
        verdict_refs = session.last_verdict.evidence_refs if session.last_verdict is not None else []
        return [ref.evidence_id for ref in verdict_refs]

    @staticmethod
    def _has_writeback_evidence(session: TaskSession) -> bool:
        if session.last_verdict is None:
            return False
        if session.last_verdict.evidence_refs:
            return True
        if session.last_execution_result is not None and session.last_execution_result.audit is not None:
            return True
        return False

    @staticmethod
    def _normalized_tags(tags: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tag in tags:
            tag = raw_tag.strip()
            if not tag:
                continue
            lowered = tag.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(tag)
        return normalized


__all__ = ["TaskMemoryRuntime"]
