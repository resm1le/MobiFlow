from __future__ import annotations

import re
from typing import Callable

from mobiflow_agent.agents.contracts import AgentRole, RoleRequest, RoleResult
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ObservationView,
    StrictModel,
    VerificationCheck,
    VerificationPredicate,
    VerificationPredicateOperator,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.common.ids import build_role_result_id
from mobiflow_agent.model.prompting import VerifierPromptBuilder
from mobiflow_agent.model.runtime import ModelRuntime
from mobiflow_agent.task.session import TaskSession


VerifierCallback = Callable[[TaskSession, ObservationView | None], VerificationVerdict]


class VerifierModelInterpretation(StrictModel):
    summary: str
    matched_check_ids: list[str] = []
    blocked_reason: str | None = None


class VerifierAgent:
    def __init__(
        self,
        *,
        model_client: ModelRuntime | None = None,
        prompt_builder: VerifierPromptBuilder | None = None,
        verifier: VerifierCallback | None = None,
        verifier_fallback: VerifierCallback | None = None,
    ):
        self._model_client = model_client
        self._prompt_builder = prompt_builder or VerifierPromptBuilder()
        self._verifier = verifier
        self._verifier_fallback = verifier_fallback

    def bind_model_runtime(self, model_client: ModelRuntime | None) -> None:
        if model_client is not None:
            self._model_client = model_client

    def verify(
        self,
        session: TaskSession,
        observation: ObservationView | None,
        request: RoleRequest | None = None,
    ) -> tuple[VerificationVerdict, RoleResult]:
        if request is not None and request.role != AgentRole.VERIFIER:
            raise ValueError("VerifierAgent received a non-verifier RoleRequest.")
        before_trace_count = len(session.model_trace)
        verdict = self._build_verdict(session, observation)
        trace_refs = [
            trace.invocation_id for trace in session.model_trace[before_trace_count:]
        ]
        result = RoleResult(
            result_id=build_role_result_id(),
            role=AgentRole.VERIFIER,
            session_id=session.session_id,
            step_id=session.current_step.step_id if session.current_step else None,
            summary=f"Verifier agent returned {verdict.status.value}.",
            payload={
                "verdict": verdict.model_dump(mode="python"),
                "model_trace_refs": trace_refs,
            },
            handoff_reason=verdict.status.value,
            next_role=AgentRole.RECOVERY if verdict.status != VerificationStatus.VERIFIED_SUCCESS else None,
        )
        return verdict, result

    def _build_verdict(self, session: TaskSession, observation: ObservationView | None) -> VerificationVerdict:
        if self._verifier is not None:
            return self._verifier(session, observation)
        interpretation = self._interpret_with_model(session, observation)
        verdict = self._build_evidence_verdict(session, observation)
        if interpretation is None:
            if self._verifier_fallback is not None:
                return self._verifier_fallback(session, observation)
            return verdict
        summary = interpretation.summary.strip()
        if verdict.status == VerificationStatus.BLOCKED:
            return verdict.model_copy(
                update={
                    "summary": summary or verdict.summary,
                    "blocked_reason": interpretation.blocked_reason or verdict.blocked_reason,
                }
            )
        if verdict.status == VerificationStatus.VERIFIED_SUCCESS:
            matched_check_ids = [
                check_id for check_id in verdict.matched_check_ids if check_id in interpretation.matched_check_ids
            ] or verdict.matched_check_ids
            return verdict.model_copy(
                update={
                    "summary": summary or verdict.summary,
                    "matched_check_ids": matched_check_ids,
                }
            )
        if summary:
            return verdict.model_copy(update={"summary": summary})
        return verdict

    def _interpret_with_model(
        self,
        session: TaskSession,
        observation: ObservationView | None,
    ) -> VerifierModelInterpretation | None:
        if self._model_client is None or session.active_model_profile is None:
            return None
        prompt = self._prompt_builder.build(session=session, observation=observation)
        try:
            generated = self._model_client.generate_structured(
                role=AgentRole.VERIFIER,
                prompt=prompt,
                response_model=VerifierModelInterpretation,
                profile_name=session.active_model_profile,
                metadata={"session_id": session.session_id},
            )
        except Exception:
            return None
        session.model_trace.append(generated.response.trace)
        return generated.output

    def _build_evidence_verdict(
        self,
        session: TaskSession,
        observation: ObservationView | None,
    ) -> VerificationVerdict:
        spec = (
            session.active_verification_spec
            or (
                session.current_step.verification_spec
                if session.current_step and session.current_step.verification_spec is not None
                else session.initial_verification_spec
            )
        )
        target_kind = (
            session.recovery_outcome.target_kind
            if session.recovery_outcome is not None and session.recovery_outcome.target_kind is not None
            else (
                spec.target_kind
                if spec is not None
                else (
                    session.current_step.verification_target_kind
                    if session.current_step and session.current_step.verification_target_kind is not None
                    else EntityKind.TASK
                )
            )
        )
        target_id = (
            session.recovery_outcome.target_id
            if session.recovery_outcome is not None and session.recovery_outcome.target_id is not None
            else (
                spec.target_id
                if spec is not None
                else (
                    session.current_step.verification_target_id
                    if session.current_step and session.current_step.verification_target_id is not None
                    else session.session_id
                )
            )
        )
        evidence_refs: list[EvidenceRef] = []
        if observation is not None:
            for fact in observation.facts:
                evidence_refs.extend(fact.evidence_refs)
        if session.recovery_outcome is not None:
            for evidence_ref in session.recovery_outcome.evidence_refs:
                if evidence_ref not in evidence_refs:
                    evidence_refs.append(evidence_ref)
        searchable_text = self._build_searchable_text(observation)
        if (
            session.recovery_outcome is not None
            and session.recovery_outcome.execution_context is None
            and session.recovery_outcome.observation is None
        ):
            return VerificationVerdict(
                verdict_id=f"task-verdict:{session.session_id}:recovery-failed",
                status=VerificationStatus.VERIFIED_FAILED,
                summary=session.recovery_outcome.summary,
                target_kind=target_kind,
                target_id=target_id,
                unmatched_check_ids=[check.check_id for check in spec.success_checks] if spec is not None else ["recovery-effective"],
                evidence_refs=evidence_refs
                or [
                    EvidenceRef(
                        evidence_id=f"recovery-note:{session.session_id}",
                        kind=EvidenceKind.INLINE_NOTE,
                        summary=session.recovery_outcome.summary,
                        locator=target_id,
                    )
                ],
            )
        if spec is not None:
            blocked_check = self._match_blocked_check(spec.blocked_checks, observation)
            if blocked_check is not None:
                return VerificationVerdict(
                    verdict_id=f"task-verdict:{session.session_id}:blocked",
                    status=VerificationStatus.BLOCKED,
                    summary=f"Verifier identified blocked check: {blocked_check.description}.",
                    target_kind=target_kind,
                    target_id=target_id,
                    unmatched_check_ids=[check.check_id for check in spec.success_checks],
                    evidence_refs=evidence_refs,
                    blocked_reason=blocked_check.check_id,
                    diagnostics=self._diagnostics(
                        observation=observation,
                        matched_check_ids=[],
                        unmatched_check_ids=[check.check_id for check in spec.success_checks],
                        blocked_reason=blocked_check.check_id,
                        missing_evidence=False,
                    ),
                )
            blocked_reason = self._match_blocked_reason(spec.blocked_conditions, searchable_text)
            if blocked_reason is not None:
                return VerificationVerdict(
                    verdict_id=f"task-verdict:{session.session_id}:blocked",
                    status=VerificationStatus.BLOCKED,
                    summary=f"Verifier identified blocked condition: {blocked_reason}.",
                    target_kind=target_kind,
                    target_id=target_id,
                    unmatched_check_ids=[check.check_id for check in spec.success_checks],
                    evidence_refs=evidence_refs,
                    blocked_reason=blocked_reason,
                    diagnostics=self._diagnostics(
                        observation=observation,
                        matched_check_ids=[],
                        unmatched_check_ids=[check.check_id for check in spec.success_checks],
                        blocked_reason=blocked_reason,
                        missing_evidence=False,
                    ),
                )
            matched_check_ids = [
                check.check_id
                for check in spec.success_checks
                if self._matches_verification_check(
                    check=check,
                    observation=observation,
                    searchable_text=searchable_text,
                    has_evidence=bool(evidence_refs),
                )
            ]
            unmatched_check_ids = [
                check.check_id for check in spec.success_checks if check.check_id not in matched_check_ids
            ]
            if matched_check_ids and not unmatched_check_ids and evidence_refs:
                return VerificationVerdict(
                    verdict_id=f"task-verdict:{session.session_id}:success",
                    status=VerificationStatus.VERIFIED_SUCCESS,
                    summary="Verifier satisfied all verification checks with observation evidence.",
                    target_kind=target_kind,
                    target_id=target_id,
                    matched_check_ids=matched_check_ids,
                    evidence_refs=evidence_refs,
                    diagnostics=self._diagnostics(
                        observation=observation,
                        matched_check_ids=matched_check_ids,
                        unmatched_check_ids=[],
                        blocked_reason=None,
                        missing_evidence=False,
                    ),
                )
            return VerificationVerdict(
                verdict_id=f"task-verdict:{session.session_id}:unknown",
                status=VerificationStatus.VERIFIED_UNKNOWN,
                summary="Verifier could not satisfy all verification checks from the current evidence.",
                target_kind=target_kind,
                target_id=target_id,
                matched_check_ids=matched_check_ids,
                unmatched_check_ids=unmatched_check_ids,
                evidence_refs=evidence_refs
                or [
                    EvidenceRef(
                        evidence_id=f"verification-note:{session.session_id}",
                        kind=EvidenceKind.INLINE_NOTE,
                        summary="Verification checks remain unmatched with the current observation.",
                        locator=session.session_id,
                    )
                ],
                diagnostics=self._diagnostics(
                    observation=observation,
                    matched_check_ids=matched_check_ids,
                    unmatched_check_ids=unmatched_check_ids,
                    blocked_reason=None,
                    missing_evidence=not bool(evidence_refs),
                ),
            )
        if evidence_refs:
            return VerificationVerdict(
                verdict_id=f"task-verdict:{session.session_id}:success",
                status=VerificationStatus.VERIFIED_SUCCESS,
                summary="Verifier found observation evidence for the active step.",
                target_kind=target_kind,
                target_id=target_id,
                matched_check_ids=["has-evidence"],
                evidence_refs=evidence_refs,
                diagnostics=self._diagnostics(
                    observation=observation,
                    matched_check_ids=["has-evidence"],
                    unmatched_check_ids=[],
                    blocked_reason=None,
                    missing_evidence=False,
                ),
            )
        return VerificationVerdict(
            verdict_id=f"task-verdict:{session.session_id}:unknown",
            status=VerificationStatus.VERIFIED_UNKNOWN,
            summary="Verifier did not find sufficient evidence for the active step.",
            target_kind=target_kind,
            target_id=target_id,
            unmatched_check_ids=["has-evidence"],
            evidence_refs=[
                EvidenceRef(
                    evidence_id=f"verification-note:{session.session_id}",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary="No evidence refs were available for verification.",
                    locator=session.session_id,
                )
            ],
            diagnostics=self._diagnostics(
                observation=observation,
                matched_check_ids=[],
                unmatched_check_ids=["has-evidence"],
                blocked_reason=None,
                missing_evidence=True,
            ),
        )

    @staticmethod
    def _build_searchable_text(observation: ObservationView | None) -> str:
        if observation is None:
            return ""
        parts: list[str] = [observation.observation_id, observation.focus_kind.value, observation.focus_id]
        for fact in observation.facts:
            parts.extend([fact.fact_id, fact.title, str(fact.value)])
            for ref in fact.evidence_refs:
                parts.extend([ref.summary])
                parts.extend(value for value in [ref.locator, ref.handle, ref.uri] if value)
        for inference in observation.inferences:
            parts.extend([inference.inference_id, inference.statement])
        return " ".join(str(part) for part in parts).casefold()

    @staticmethod
    def _match_blocked_reason(blocked_conditions: list[str], searchable_text: str) -> str | None:
        for blocked_condition in blocked_conditions:
            if blocked_condition.casefold() in searchable_text:
                return blocked_condition
        return None

    @staticmethod
    def _match_blocked_check(
        blocked_checks: list[VerificationCheck],
        observation: ObservationView | None,
    ) -> VerificationCheck | None:
        if observation is None:
            return None
        searchable_text = VerifierAgent._build_searchable_text(observation)
        for check in blocked_checks:
            if VerifierAgent._matches_verification_check(
                check=check,
                observation=observation,
                searchable_text=searchable_text,
                has_evidence=True,
            ):
                return check
        return None

    @staticmethod
    def _matches_check(
        *,
        check_id: str,
        description: str,
        evidence_hint: str | None,
        searchable_text: str,
        has_evidence: bool,
    ) -> bool:
        if check_id == "has-evidence":
            return has_evidence
        candidates = [check_id, description]
        if evidence_hint is not None:
            candidates.append(evidence_hint)
        for candidate in candidates:
            if VerifierAgent._candidate_matches(candidate, searchable_text):
                return True
        return False

    @staticmethod
    def _matches_verification_check(
        *,
        check: VerificationCheck,
        observation: ObservationView | None,
        searchable_text: str,
        has_evidence: bool,
    ) -> bool:
        if check.predicates:
            return all(
                VerifierAgent._matches_predicate(predicate, observation)
                for predicate in check.predicates
            )
        return VerifierAgent._matches_check(
            check_id=check.check_id,
            description=check.description,
            evidence_hint=check.evidence_hint,
            searchable_text=searchable_text,
            has_evidence=has_evidence,
        )

    @staticmethod
    def _matches_predicate(predicate: VerificationPredicate, observation: ObservationView | None) -> bool:
        if observation is None:
            return False
        candidate_facts = [
            fact
            for fact in observation.facts
            if predicate.fact_id is None or fact.fact_id == predicate.fact_id
        ]
        for fact in candidate_facts:
            values = VerifierAgent._resolve_path(fact.model_dump(mode="python"), predicate.field_path)
            if VerifierAgent._predicate_values_match(predicate, values):
                return True
        return False

    @staticmethod
    def _resolve_path(payload, field_path: str) -> list:
        values = [payload]
        for raw_part in field_path.split("."):
            expand_list = raw_part.endswith("[]")
            part = raw_part[:-2] if expand_list else raw_part
            next_values = []
            for value in values:
                if isinstance(value, dict) and part in value:
                    resolved = value[part]
                else:
                    continue
                if expand_list and isinstance(resolved, list):
                    next_values.extend(resolved)
                else:
                    next_values.append(resolved)
            values = next_values
            if not values:
                break
        return values

    @staticmethod
    def _predicate_values_match(predicate: VerificationPredicate, values: list) -> bool:
        if predicate.operator == VerificationPredicateOperator.EXISTS:
            return bool(values)
        if predicate.operator in {
            VerificationPredicateOperator.ANY_EQUALS,
            VerificationPredicateOperator.ANY_CONTAINS,
        }:
            values = [
                item
                for value in values
                for item in (value if isinstance(value, list) else [value])
            ]
        return any(VerifierAgent._predicate_value_matches(predicate, value) for value in values)

    @staticmethod
    def _predicate_value_matches(predicate: VerificationPredicate, value) -> bool:
        operator = predicate.operator
        if operator in {VerificationPredicateOperator.EQUALS, VerificationPredicateOperator.ANY_EQUALS}:
            return VerifierAgent._normalize_predicate_value(value, predicate.case_sensitive) == VerifierAgent._normalize_predicate_value(
                predicate.expected,
                predicate.case_sensitive,
            )
        if operator in {VerificationPredicateOperator.CONTAINS, VerificationPredicateOperator.ANY_CONTAINS}:
            if predicate.expected is None:
                return False
            haystack = str(value)
            needle = str(predicate.expected)
            if not predicate.case_sensitive:
                haystack = haystack.casefold()
                needle = needle.casefold()
            return needle in haystack
        return False

    @staticmethod
    def _normalize_predicate_value(value, case_sensitive: bool):
        if isinstance(value, str) and not case_sensitive:
            return value.casefold()
        return value

    @staticmethod
    def _diagnostics(
        *,
        observation: ObservationView | None,
        matched_check_ids: list[str],
        unmatched_check_ids: list[str],
        blocked_reason: str | None,
        missing_evidence: bool,
    ) -> dict:
        suspected_state = None
        if observation is not None:
            for fact in observation.facts:
                if fact.fact_id == "simulated_screen_snapshot" and isinstance(fact.value, dict):
                    suspected_state = fact.value.get("title") or fact.value.get("screen_id")
                    break
        suggested = "continue_verification"
        if blocked_reason is not None:
            suggested = "recover_or_handoff"
        elif missing_evidence or unmatched_check_ids:
            suggested = "observe_or_recover"
        return {
            "suspected_current_state": suspected_state,
            "matched_check_ids": matched_check_ids,
            "unmatched_check_ids": unmatched_check_ids,
            "blocked_reason": blocked_reason,
            "missing_evidence": missing_evidence,
            "suggested_recovery_direction": suggested,
        }

    @staticmethod
    def _candidate_matches(candidate: str, searchable_text: str) -> bool:
        normalized = candidate.casefold()
        if normalized and normalized in searchable_text:
            return True
        tokens = [token for token in re.split(r"[^a-z0-9]+", normalized) if token and len(token) >= 3]
        return bool(tokens) and all(token in searchable_text for token in tokens)
