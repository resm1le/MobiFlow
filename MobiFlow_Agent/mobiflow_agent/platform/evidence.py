from __future__ import annotations

from typing import Any

from mobiflow_agent.common.contracts import (
    EvidenceKind,
    EvidenceRef,
    ObservationFact,
    ObservationFactSource,
    ObservationInference,
    ObservationView,
)

RUN_GOVERNANCE_FACT_ID = "run_governance_snapshot"
RUN_LINEAGE_FACT_ID = "run_lineage_snapshot"
RUN_ARTIFACTS_FACT_ID = "run_latest_artifacts"
ATTEMPT_DIAGNOSIS_FACT_ID = "attempt_diagnosis_bundle"
ATTEMPT_EVENTS_FACT_ID = "attempt_key_events"
ATTEMPT_FAILURE_FACT_ID = "attempt_failure_signals"


def build_run_observation_view(
    run_id: str,
    governance_response: dict[str, Any],
    lineage_response: dict[str, Any],
    diagnosis_response: dict[str, Any] | None = None,
) -> ObservationView:
    governance_result = governance_response.get("result") or {}
    lineage_result = lineage_response.get("result") or {}
    diagnosis_result = (diagnosis_response or {}).get("result") or {}

    facts: list[ObservationFact] = [
        ObservationFact(
            fact_id=RUN_GOVERNANCE_FACT_ID,
            source=ObservationFactSource.PLATFORM,
            title="Run governance snapshot",
            value=governance_result,
            evidence_refs=_snapshot_evidence("get_run_governance_snapshot", f"run:{run_id}", governance_response),
        ),
        ObservationFact(
            fact_id=RUN_LINEAGE_FACT_ID,
            source=ObservationFactSource.PLATFORM,
            title="Run lineage snapshot",
            value=lineage_result,
            evidence_refs=_snapshot_evidence("get_run_lineage_snapshot", f"run:{run_id}", lineage_response),
        ),
    ]
    handles = _collect_resource_handles(lineage_result.get("latestArtifacts") or [])
    artifact_refs = _artifact_evidence_refs(lineage_result.get("latestArtifacts") or [])
    if artifact_refs:
        facts.append(
            ObservationFact(
                fact_id=RUN_ARTIFACTS_FACT_ID,
                source=ObservationFactSource.PLATFORM,
                title="Run latest artifacts",
                value=lineage_result.get("latestArtifacts") or [],
                evidence_refs=artifact_refs,
            )
        )
    if diagnosis_response is not None:
        facts.extend(_diagnosis_facts(diagnosis_result, diagnosis_response))

    inferences = _build_run_inferences(run_id, governance_result, lineage_result, diagnosis_result)
    return ObservationView(
        observation_id=f"observation:run:{run_id}",
        focus_kind="run",
        focus_id=run_id,
        facts=facts,
        inferences=inferences,
        resource_handles=handles,
        observed_at_ms=max(
            int(governance_result.get("lastUpdatedAt") or 0),
            _latest_artifact_created_at(lineage_result.get("latestArtifacts") or []),
        )
        or None,
    )


def build_attempt_observation_view(attempt_id: str, diagnosis_response: dict[str, Any]) -> ObservationView:
    diagnosis_result = diagnosis_response.get("result") or {}
    facts = _diagnosis_facts(diagnosis_result, diagnosis_response)
    return ObservationView(
        observation_id=f"observation:attempt:{attempt_id}",
        focus_kind="attempt",
        focus_id=attempt_id,
        facts=facts,
        inferences=_build_attempt_inferences(attempt_id, diagnosis_result),
    )


def get_fact_value(observation: ObservationView | None, fact_id: str) -> Any | None:
    if observation is None:
        return None
    for fact in observation.facts:
        if fact.fact_id == fact_id:
            return fact.value
    return None


def get_fact(observation: ObservationView | None, fact_id: str) -> ObservationFact | None:
    if observation is None:
        return None
    for fact in observation.facts:
        if fact.fact_id == fact_id:
            return fact
    return None


def build_confirmation_evidence(confirmation_id: str, summary: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"confirmation:{confirmation_id}",
        kind=EvidenceKind.USER_CONFIRMATION,
        summary=summary,
        locator=confirmation_id,
    )


def _diagnosis_facts(diagnosis_result: dict[str, Any], diagnosis_response: dict[str, Any]) -> list[ObservationFact]:
    attempt_id = diagnosis_result.get("attemptId", "unknown-attempt")
    diagnosis_evidence = _snapshot_evidence(
        "get_attempt_diagnosis_bundle",
        f"attempt:{attempt_id}",
        diagnosis_response,
    )
    facts = [
        ObservationFact(
            fact_id=ATTEMPT_DIAGNOSIS_FACT_ID,
            source=ObservationFactSource.PLATFORM,
            title="Attempt diagnosis bundle",
            value=diagnosis_result,
            evidence_refs=diagnosis_evidence,
        )
    ]
    key_events = diagnosis_result.get("keyEvents") or []
    if key_events:
        facts.append(
            ObservationFact(
                fact_id=ATTEMPT_EVENTS_FACT_ID,
                source=ObservationFactSource.PLATFORM,
                title="Attempt key events",
                value=key_events,
                evidence_refs=[
                    EvidenceRef(
                        evidence_id=f"event:{attempt_id}:{index}",
                        kind=EvidenceKind.EVENT,
                        summary=(event.get("message") or event.get("eventType") or f"Event {index}"),
                        locator=f"{attempt_id}:{index}",
                    )
                    for index, event in enumerate(key_events)
                ],
            )
        )
    failure_signals = diagnosis_result.get("failureSignals") or []
    if failure_signals:
        facts.append(
            ObservationFact(
                fact_id=ATTEMPT_FAILURE_FACT_ID,
                source=ObservationFactSource.PLATFORM,
                title="Attempt failure signals",
                value=failure_signals,
                evidence_refs=diagnosis_evidence,
            )
        )
    return facts


def _build_run_inferences(
    run_id: str,
    governance_result: dict[str, Any],
    lineage_result: dict[str, Any],
    diagnosis_result: dict[str, Any],
) -> list[ObservationInference]:
    inferences: list[ObservationInference] = []
    blockers = governance_result.get("blockers") or []
    if governance_result.get("status") == "BLOCKED" or blockers:
        inferences.append(
            ObservationInference(
                inference_id=f"inference:run:{run_id}:blocked",
                statement=f"Run {run_id} is currently blocked.",
                based_on_fact_ids=[RUN_GOVERNANCE_FACT_ID],
                confidence=0.94,
            )
        )
    governed_options = lineage_result.get("currentGovernedOptions") or []
    if "cancel_run" in governed_options:
        inferences.append(
            ObservationInference(
                inference_id=f"inference:run:{run_id}:cancel-available",
                statement=f"Run {run_id} currently exposes cancel_run as a governed option.",
                based_on_fact_ids=[RUN_LINEAGE_FACT_ID],
                confidence=0.91,
            )
        )
    if diagnosis_result.get("failureSignals"):
        inferences.append(
            ObservationInference(
                inference_id=f"inference:run:{run_id}:failure-signals",
                statement=f"Latest attempt for run {run_id} exposes structured failure signals.",
                based_on_fact_ids=[ATTEMPT_DIAGNOSIS_FACT_ID],
                confidence=0.82,
            )
        )
    return inferences


def _build_attempt_inferences(attempt_id: str, diagnosis_result: dict[str, Any]) -> list[ObservationInference]:
    if diagnosis_result.get("failureSignals"):
        return [
            ObservationInference(
                inference_id=f"inference:attempt:{attempt_id}:failure-signals",
                statement=f"Attempt {attempt_id} exposes structured failure signals.",
                based_on_fact_ids=[ATTEMPT_DIAGNOSIS_FACT_ID],
                confidence=0.82,
            )
        ]
    return []


def _snapshot_evidence(tool_name: str, entity_locator: str, response: dict[str, Any]) -> list[EvidenceRef]:
    evidence = [
        EvidenceRef(
            evidence_id=f"snapshot:{tool_name}:{entity_locator}",
            kind=EvidenceKind.PLATFORM_SNAPSHOT,
            summary=f"Snapshot from {tool_name} for {entity_locator}.",
            locator=entity_locator,
        )
    ]
    audit = response.get("audit") or {}
    audit_id = audit.get("auditId")
    if audit_id:
        evidence.append(
            EvidenceRef(
                evidence_id=f"audit:{audit_id}",
                kind=EvidenceKind.AUDIT,
                summary=f"Tool audit {audit_id}.",
                locator=audit_id,
            )
        )
    confirmation = response.get("confirmation") or {}
    confirmation_id = confirmation.get("confirmationId")
    if confirmation_id:
        evidence.append(
            EvidenceRef(
                evidence_id=f"confirmation:{confirmation_id}",
                kind=EvidenceKind.USER_CONFIRMATION,
                summary=confirmation.get("summary") or f"Confirmation {confirmation_id}.",
                locator=confirmation_id,
            )
        )
    return evidence


def _artifact_evidence_refs(artifacts: list[dict[str, Any]]) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    for artifact in artifacts:
        resource = artifact.get("resource") or {}
        handle = resource.get("handle")
        if not handle:
            continue
        artifact_id = artifact.get("artifactId", handle)
        refs.append(
            EvidenceRef(
                evidence_id=f"artifact:{artifact_id}",
                kind=EvidenceKind.ARTIFACT,
                summary=f"{artifact.get('artifactType', 'artifact')} {artifact.get('fileName') or artifact_id}.",
                locator=artifact_id,
                handle=handle,
            )
        )
    return refs


def _collect_resource_handles(artifacts: list[dict[str, Any]]) -> list[str]:
    handles = []
    for artifact in artifacts:
        resource = artifact.get("resource") or {}
        handle = resource.get("handle")
        if handle:
            handles.append(handle)
    return handles


def _latest_artifact_created_at(artifacts: list[dict[str, Any]]) -> int:
    return max((int(artifact.get("createdAt") or 0) for artifact in artifacts), default=0)
