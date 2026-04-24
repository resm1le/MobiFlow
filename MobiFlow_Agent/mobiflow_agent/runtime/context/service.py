from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Callable

from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.runtime.context.estimation import estimate_text_tokens, estimate_tokens, serialize_context
from mobiflow_agent.runtime.context.models import (
    ContextCompressionResult,
    ContextHandoff,
    SessionContextDigest,
    StepContextSummary,
)
from mobiflow_agent.runtime.context.policy import ContextCompressionPolicy

if TYPE_CHECKING:
    from mobiflow_agent.task.session import TaskSession


HistorySummarizer = Callable[[list[StepContextSummary]], str | None]


class ContextCompressionService:
    def __init__(
        self,
        *,
        policy: ContextCompressionPolicy | None = None,
    ) -> None:
        self._policy = policy or ContextCompressionPolicy()

    def estimate_tokens(self, value: Any) -> int:
        return estimate_tokens(value)

    def summarize_current_step(self, session: TaskSession) -> StepContextSummary | None:
        step = session.current_step
        if step is None:
            return None
        evidence_ref_ids = self._evidence_ref_ids(session)
        matched_check_ids = list(session.last_verdict.matched_check_ids) if session.last_verdict is not None else []
        outcome_status = (
            session.last_verdict.status.value
            if session.last_verdict is not None
            else session.status.value
        )
        summary = self._step_summary_text(session)
        return StepContextSummary(
            step_id=step.step_id,
            step_kind=step.kind.value,
            goal=step.goal,
            outcome_status=outcome_status,
            summary=summary,
            blocked_reason=session.last_verdict.blocked_reason if session.last_verdict is not None else None,
            matched_check_ids=matched_check_ids,
            evidence_ref_ids=evidence_ref_ids,
        )

    def refresh_session_context(
        self,
        session: TaskSession,
        *,
        history_summarizer: HistorySummarizer | None = None,
    ) -> None:
        step_summary = self.summarize_current_step(session)
        if step_summary is not None:
            session.step_summaries[step_summary.step_id] = step_summary
        session.session_digest = self.build_session_digest(
            session,
            history_summarizer=history_summarizer,
        )

    def build_session_digest(
        self,
        session: TaskSession,
        *,
        history_summarizer: HistorySummarizer | None = None,
    ) -> SessionContextDigest:
        summaries = list(session.step_summaries.values())
        recent = summaries[-self._policy.max_recent_step_summaries :]
        older = summaries[: max(len(summaries) - len(recent), 0)]
        historical_summary = None
        if older:
            historical_summary = (
                history_summarizer(older)
                if history_summarizer is not None
                else self._default_history_summary(older)
            )
        pending_approval_summary = self._pending_approval_summary(session)
        recovery_summary = session.recovery_outcome.summary if session.recovery_outcome is not None else session.recovery_state
        memory_highlights = self._compact_mapping(session.memory_context, max_items=self._policy.max_memory_items)
        evaluation_highlights = self._compact_mapping(
            session.evaluation_context,
            max_items=self._policy.max_evaluation_items,
        )
        open_risks = self._open_risks(session)
        digest = SessionContextDigest(
            summary=self._session_summary_text(session, recent, pending_approval_summary, recovery_summary, open_risks),
            recent_step_summaries=recent,
            historical_summary=historical_summary,
            pending_approval_summary=pending_approval_summary,
            recovery_summary=recovery_summary,
            open_risks=open_risks,
            memory_highlights=memory_highlights,
            evaluation_highlights=evaluation_highlights,
        )
        return digest.model_copy(update={"context_token_estimate": estimate_tokens(digest.model_dump(mode="python"))})

    def export_context_handoff(self, session: TaskSession) -> ContextHandoff:
        digest = session.session_digest or self.build_session_digest(session)
        return ContextHandoff(
            source_session_id=session.session_id,
            goal=session.goal,
            target_kind=session.target_kind,
            target_id=session.target_id,
            session_digest=digest,
            latest_verdict_summary=session.last_verdict.summary if session.last_verdict is not None else None,
            resume_hint=self._resume_hint(session),
            created_at=int(time.time()),
        )

    def apply_context_handoff(self, session: TaskSession, handoff: ContextHandoff) -> TaskSession:
        session.imported_handoff = handoff
        session.session_digest = handoff.session_digest
        session.target_kind = session.target_kind or handoff.target_kind
        session.target_id = session.target_id or handoff.target_id
        if not session.goal:
            session.goal = handoff.goal
        return session

    def compact_prompt(
        self,
        *,
        system_prompt: str,
        payload: dict[str, Any],
        preserve_keys: list[str],
        input_token_budget: int | None,
        compaction_target_tokens: int | None,
        summary_profile: str | None = None,
        history_summarizer: HistorySummarizer | None = None,
    ) -> ContextCompressionResult:
        before = estimate_tokens(payload)
        compacted_payload = dict(payload)
        compacted = False
        target_budget = compaction_target_tokens or input_token_budget
        if target_budget is not None and before > target_budget:
            compacted_payload = self._compact_payload(compacted_payload, preserve_keys=preserve_keys)
            compacted = True
        after = estimate_tokens(compacted_payload)
        used_summary_profile = None
        if (
            target_budget is not None
            and after > target_budget
            and summary_profile is not None
            and history_summarizer is not None
        ):
            compacted_payload = self._summarize_history(compacted_payload, history_summarizer)
            compacted = True
            after = estimate_tokens(compacted_payload)
            used_summary_profile = summary_profile
        if target_budget is not None and after > target_budget:
            compacted_payload = self._hard_trim_payload(compacted_payload, preserve_keys=preserve_keys)
            compacted = True
            after = estimate_tokens(compacted_payload)
        user_prompt = serialize_context(compacted_payload)
        total_after = estimate_text_tokens(system_prompt) + after
        total_before = estimate_text_tokens(system_prompt) + before
        return ContextCompressionResult(
            user_prompt=user_prompt,
            context_payload=compacted_payload,
            compacted=compacted,
            estimated_input_tokens_before=total_before,
            estimated_input_tokens_after=total_after,
            used_summary_profile=used_summary_profile,
            used_imported_handoff=payload.get("imported_handoff") is not None,
        )

    def _compact_payload(self, payload: dict[str, Any], *, preserve_keys: list[str]) -> dict[str, Any]:
        compacted: dict[str, Any] = {}
        for key, value in payload.items():
            if key in preserve_keys:
                compacted[key] = value
                continue
            compacted[key] = self._trim_value(value)
        return compacted

    def _hard_trim_payload(self, payload: dict[str, Any], *, preserve_keys: list[str]) -> dict[str, Any]:
        trimmed: dict[str, Any] = {}
        for key, value in payload.items():
            if key in preserve_keys:
                trimmed[key] = value
            elif key in {"session_digest", "imported_handoff", "memory_context", "evaluation_context"}:
                trimmed[key] = self._trim_value(value, aggressive=True)
            else:
                trimmed[key] = self._trim_value(value)
        return trimmed

    def _summarize_history(
        self,
        payload: dict[str, Any],
        history_summarizer: HistorySummarizer,
    ) -> dict[str, Any]:
        summarized = dict(payload)
        history_items = []
        digest = summarized.get("session_digest")
        if isinstance(digest, dict):
            raw_summaries = digest.get("recent_step_summaries") or []
            for item in raw_summaries:
                try:
                    history_items.append(StepContextSummary.model_validate(item))
                except Exception:
                    continue
            summary = history_summarizer(history_items)
            if summary:
                digest = dict(digest)
                digest["historical_summary"] = summary
                if len(raw_summaries) > 1:
                    digest["recent_step_summaries"] = raw_summaries[-1:]
                summarized["session_digest"] = digest
        return summarized

    def _trim_value(self, value: Any, *, aggressive: bool = False) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            limit = self._policy.max_string_chars // (2 if aggressive else 1)
            return value if len(value) <= limit else value[: max(limit - 3, 1)] + "..."
        if isinstance(value, list):
            limit = max(self._policy.max_list_items // (2 if aggressive else 1), 1)
            return [self._trim_value(item, aggressive=aggressive) for item in value[:limit]]
        if isinstance(value, dict):
            limit = max(self._policy.max_dict_items // (2 if aggressive else 1), 1)
            trimmed: dict[str, Any] = {}
            for index, (key, nested) in enumerate(value.items()):
                if index >= limit:
                    break
                trimmed[key] = self._trim_value(nested, aggressive=aggressive)
            return trimmed
        if hasattr(value, "model_dump"):
            return self._trim_value(value.model_dump(mode="python"), aggressive=aggressive)
        return value

    def _compact_mapping(self, mapping: dict[str, Any], *, max_items: int) -> dict[str, Any]:
        compacted: dict[str, Any] = {}
        for index, (key, value) in enumerate(mapping.items()):
            if index >= max_items:
                break
            compacted[key] = self._trim_value(value)
        return compacted

    @staticmethod
    def _evidence_ref_ids(session: TaskSession) -> list[str]:
        if session.last_observation is None:
            return []
        evidence_ids: list[str] = []
        for fact in session.last_observation.facts:
            for evidence_ref in fact.evidence_refs:
                if evidence_ref.evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_ref.evidence_id)
        if session.recovery_outcome is not None:
            for evidence_ref in session.recovery_outcome.evidence_refs:
                if evidence_ref.evidence_id not in evidence_ids:
                    evidence_ids.append(evidence_ref.evidence_id)
        return evidence_ids

    @staticmethod
    def _default_history_summary(older: list[StepContextSummary]) -> str:
        return " ".join(summary.summary for summary in older)

    @staticmethod
    def _open_risks(session: TaskSession) -> list[str]:
        risks: list[str] = []
        if session.pending_execution is not None:
            risks.append("approval_pending")
        if session.last_verdict is not None and session.last_verdict.status in {
            VerificationStatus.BLOCKED,
            VerificationStatus.VERIFIED_FAILED,
            VerificationStatus.VERIFIED_UNKNOWN,
        }:
            risks.append(session.last_verdict.status.value)
        if session.recovery_outcome is not None and session.recovery_outcome.execution_context is None:
            risks.append("recovery_unresolved")
        return risks

    @staticmethod
    def _pending_approval_summary(session: TaskSession) -> str | None:
        if session.pending_execution is None or session.pending_execution.confirmation_summary is None:
            return None
        return session.pending_execution.confirmation_summary

    @staticmethod
    def _resume_hint(session: TaskSession) -> str:
        if session.pending_execution is not None:
            return "resume_after_approval"
        if session.last_verdict is not None and session.last_verdict.status == VerificationStatus.BLOCKED:
            return "resume_from_blocked_context"
        return "resume_from_session_digest"

    @staticmethod
    def _session_summary_text(
        session: TaskSession,
        recent: list[StepContextSummary],
        pending_approval_summary: str | None,
        recovery_summary: str | None,
        open_risks: list[str],
    ) -> str:
        parts = [f"Task goal: {session.goal}."]
        if recent:
            parts.append(f"Recent progress: {recent[-1].summary}")
        if pending_approval_summary:
            parts.append(f"Pending approval: {pending_approval_summary}")
        if recovery_summary:
            parts.append(f"Recovery state: {recovery_summary}")
        if open_risks:
            parts.append("Open risks: " + ", ".join(open_risks) + ".")
        return " ".join(parts)

    @staticmethod
    def _step_summary_text(session: TaskSession) -> str:
        step = session.current_step
        if step is None:
            return "No active step context was available."
        if session.last_verdict is not None:
            return f"Step {step.kind.value} ended with {session.last_verdict.status.value}: {session.last_verdict.summary}"
        if session.last_execution_result is not None:
            return (
                f"Step {step.kind.value} produced execution state "
                f"{session.last_execution_result.state.value} for {session.last_execution_result.action_tool_name}."
            )
        if session.last_observation is not None:
            return f"Step {step.kind.value} refreshed observation {session.last_observation.observation_id}."
        return f"Step {step.kind.value} completed for goal: {step.goal}"


__all__ = ["ContextCompressionService", "HistorySummarizer"]
