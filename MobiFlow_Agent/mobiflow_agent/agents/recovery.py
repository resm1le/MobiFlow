from __future__ import annotations

from typing import Callable

from mobiflow_agent.agents.contracts import (
    AgentRole,
    RecoveryOutcome,
    ReplanDecision,
    ReplanDecisionType,
    RoleRequest,
    RoleResult,
)
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.common.ids import build_role_result_id
from mobiflow_agent.execution.recovery.triage import FailureTriageGuidanceService
from mobiflow_agent.model.prompting import RecoveryPromptBuilder
from mobiflow_agent.model.runtime import ModelRuntime
from mobiflow_agent.platform.types import RecoveryGuidance
from mobiflow_agent.runtime.state import RecoveryExecutionContext
from mobiflow_agent.task.session import TaskSession


RecoveryCallback = Callable[[TaskSession, object | None], RecoveryOutcome]


class RecoveryAgent:
    def __init__(
        self,
        *,
        model_client: ModelRuntime | None = None,
        prompt_builder: RecoveryPromptBuilder | None = None,
        recovery: RecoveryCallback | None = None,
        triage_service: FailureTriageGuidanceService | None = None,
    ):
        self._model_client = model_client
        self._prompt_builder = prompt_builder or RecoveryPromptBuilder()
        self._recovery = recovery
        self._triage_service = triage_service

    def bind_model_runtime(self, model_client: ModelRuntime | None) -> None:
        if model_client is not None:
            self._model_client = model_client

    def recover(
        self,
        session: TaskSession,
        failure_verdict,
        request: RoleRequest | None = None,
    ) -> tuple[RecoveryOutcome, RoleResult]:
        if request is not None and request.role != AgentRole.RECOVERY:
            raise ValueError("RecoveryAgent received a non-recovery RoleRequest.")
        before_trace_count = len(session.model_trace)
        outcome = self._build_outcome(session, failure_verdict)
        trace_refs = [
            trace.invocation_id for trace in session.model_trace[before_trace_count:]
        ]
        result = RoleResult(
            result_id=build_role_result_id(),
            role=AgentRole.RECOVERY,
            session_id=session.session_id,
            step_id=session.current_step.step_id if session.current_step else None,
            summary=outcome.summary,
            payload={
                "recovery_outcome": outcome.model_dump(mode="python"),
                "model_trace_refs": trace_refs,
            },
            handoff_reason="recovery_complete",
            next_role=AgentRole.VERIFIER,
        )
        return outcome, result

    def _build_outcome(self, session: TaskSession, failure_verdict) -> RecoveryOutcome:
        if self._recovery is not None:
            return self._recovery(session, failure_verdict)
        if self._model_client is not None and session.active_model_profile is not None:
            prompt = self._prompt_builder.build(session=session, failure_verdict=failure_verdict)
            try:
                generated = self._model_client.generate_structured(
                    role=AgentRole.RECOVERY,
                    prompt=prompt,
                    response_model=RecoveryOutcome,
                    profile_name=session.active_model_profile,
                    metadata={"session_id": session.session_id},
                )
            except Exception as exc:
                raise ValueError("RecoveryAgent model output failed validation.") from exc
            session.model_trace.append(generated.response.trace)
            return generated.output
        triage = self._build_triage(session)
        memory_hint = self._memory_guidance(session)
        target_kind = failure_verdict.target_kind if failure_verdict is not None else session.target_kind or EntityKind.TASK
        target_id = failure_verdict.target_id if failure_verdict is not None else session.target_id or session.session_id
        summary = "Recovery could not produce a corrective execution path from the current failure context."
        evidence_refs = list(failure_verdict.evidence_refs) if failure_verdict is not None else []
        guidance = None
        execution_context = None
        blocked_reason = getattr(failure_verdict, "blocked_reason", None)
        if blocked_reason in {"dynamic_recovery_retry", "slow_loading_screen"}:
            summary = "Recovery requested retrying the current dynamic step."
            if blocked_reason == "slow_loading_screen":
                summary = "Recovery requested a fresh observation after a slow loading screen."
            return RecoveryOutcome(
                summary=summary,
                target_kind=target_kind,
                target_id=target_id,
                replan_decision=ReplanDecision(
                    decision_type=ReplanDecisionType.RETRY_CURRENT_STEP,
                    summary=summary,
                ),
                evidence_refs=evidence_refs
                or [
                    EvidenceRef(
                        evidence_id=f"replan-note:{session.session_id}",
                        kind=EvidenceKind.INLINE_NOTE,
                        summary=summary,
                        locator=target_id,
                    )
                ],
            )
        if memory_hint is not None:
            guidance = memory_hint["guidance"]
            summary = memory_hint["summary"]
            execution_context = memory_hint["execution_context"]
        elif triage is not None:
            guidance = triage["guidance"]
            summary = triage["summary"]
            evidence_refs.append(
                EvidenceRef(
                    evidence_id=f"triage:{triage['triage_result_id']}",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary=summary,
                    locator=triage["run_target_id"],
                )
            )
            if triage["run_target_id"] and triage["run_id"]:
                execution_context = RecoveryExecutionContext(
                    run_target_id=triage["run_target_id"],
                    source_run_id=triage["run_id"],
                    action_name=guidance.recommended_action,
                    recommended_action=guidance.recommended_action,
                    proposal_id=f"recovery-proposal:{session.session_id}",
                )
        if not evidence_refs:
            evidence_refs = [
                EvidenceRef(
                    evidence_id=f"recovery-note:{session.session_id}",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary=summary,
                    locator=target_id,
                )
            ]
        verification_spec = (
            VerificationSpec(
                verification_id=f"verification:recovery:{session.session_id}",
                target_kind=target_kind,
                target_id=target_id,
                success_checks=[
                    VerificationCheck(
                        check_id="recovery-effective",
                        description="The recovery path is proven effective by evidence.",
                        evidence_hint="recovery evidence",
                    )
                ],
            )
            if guidance is not None and execution_context is not None
            else None
        )
        return RecoveryOutcome(
            summary=summary,
            target_kind=target_kind,
            target_id=target_id,
            guidance=guidance,
            execution_context=execution_context,
            verification_spec=verification_spec,
            evidence_refs=evidence_refs,
        )

    def _build_triage(self, session: TaskSession) -> dict | None:
        if self._triage_service is None:
            return None
        if session.target_kind != EntityKind.RUN_TARGET or session.target_id is None:
            return None
        response = self._triage_service.analyze(session.target_id)
        return {
            "run_target_id": response.run_target_id,
            "run_id": response.run_id,
            "triage_result_id": response.triage.triage_result_id,
            "summary": response.summary,
            "guidance": response.recovery_guidance,
        }

    @staticmethod
    def _memory_guidance(session: TaskSession) -> dict | None:
        step_id = session.current_step.step_id if session.current_step is not None else "recovery"
        context = session.memory_context.get(step_id) or session.memory_context.get(AgentRole.RECOVERY.value)
        if not isinstance(context, dict):
            return None
        matches = context.get("matches")
        if not isinstance(matches, list) or not matches:
            return None
        for match in matches:
            if not isinstance(match, dict):
                continue
            record = match.get("record")
            if not isinstance(record, dict):
                continue
            payload = record.get("content_payload")
            if not isinstance(payload, dict):
                continue
            guidance_payload = payload.get("recovery_guidance")
            if not isinstance(guidance_payload, dict):
                continue
            try:
                guidance = RecoveryGuidance.model_validate(guidance_payload)
            except Exception:
                continue
            execution_context = None
            if session.target_id is not None:
                execution_context = RecoveryExecutionContext(
                    run_target_id=session.target_id,
                    source_run_id=session.target_id,
                    action_name=guidance.recommended_action,
                    recommended_action=guidance.recommended_action,
                    proposal_id=f"memory-recovery:{session.session_id}",
                )
            return {
                "guidance": guidance,
                "summary": (
                    "Recovery reused a prior task memory pattern with matching recovery guidance."
                ),
                "execution_context": execution_context,
            }
        return None
