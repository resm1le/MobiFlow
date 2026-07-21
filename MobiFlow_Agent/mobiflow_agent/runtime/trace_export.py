from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mobiflow_agent.task.session import TaskSession


SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "model_response",
    "password",
    "prompt",
    "provider_response",
    "raw_prompt",
    "secret",
    "session_dump",
    "token",
}


class ExecutionTraceExporter:
    def export_json(self, session: TaskSession, *, action_traces: list[Any] | None = None) -> dict[str, Any]:
        payload = {
            "session_id": session.session_id,
            "goal": session.goal,
            "status": session.status.value,
            "completion_verdict": (
                session.completion_verdict.value if session.completion_verdict is not None else None
            ),
            "status_history": [status.value for status in session.status_history],
            "plan": None if session.plan is None else self._redact(session.plan.model_dump(mode="json")),
            "current_step": None
            if session.current_step is None
            else self._redact(session.current_step.model_dump(mode="json")),
            "step_decisions": [
                self._redact(decision.model_dump(mode="json")) for decision in session.step_decisions
            ],
            "role_requests": [
                self._redact(request.model_dump(mode="json")) for request in session.role_requests
            ],
            "role_results": [
                self._redact(result.model_dump(mode="json")) for result in session.role_results
            ],
            "last_observation": None
            if session.last_observation is None
            else self._redact(session.last_observation.model_dump(mode="json")),
            "last_execution_result": None
            if session.last_execution_result is None
            else self._redact(session.last_execution_result.model_dump(mode="json")),
            "pending_execution": None
            if session.pending_execution is None
            else self._redact(session.pending_execution.model_dump(mode="json")),
            "last_verdict": None if session.last_verdict is None else self._redact(session.last_verdict.model_dump(mode="json")),
            "recovery_outcome": None
            if session.recovery_outcome is None
            else self._redact(session.recovery_outcome.model_dump(mode="json")),
            "memory_context_keys": sorted(session.memory_context),
            "memory_highlights": self._memory_highlights(session.memory_context),
            "memory_writeback": self._redact(session.memory_context.get("memory_writeback:last")),
            "model_trace": [
                self._redact(trace.model_dump(mode="json")) for trace in session.model_trace
            ],
            "action_traces": [self._redact(self._dump_model(trace)) for trace in action_traces or []],
        }
        payload["waypoint_segments"] = self._build_waypoint_segments(session)
        payload["timeline"] = self._build_timeline(payload)
        return self._redact(payload)

    def export_markdown(self, session: TaskSession, *, action_traces: list[Any] | None = None) -> str:
        trace = self.export_json(session, action_traces=action_traces)
        lines = [
            f"# Execution Trace: {trace['session_id']}",
            "",
            f"- Goal: {trace['goal']}",
            f"- Status: {trace['status']}",
            f"- Completion: {trace['completion_verdict'] or 'none'}",
            f"- Status history: {', '.join(trace['status_history'])}",
            "",
            "## Plan",
        ]
        plan = trace["plan"] or {}
        lines.append(plan.get("summary", "(no plan)"))
        for step in plan.get("steps", []):
            lines.append(f"- {step.get('step_id')}: {step.get('kind')} - {step.get('goal')}")
        lines.extend(["", "## Decisions"])
        if trace["step_decisions"]:
            for decision in trace["step_decisions"]:
                lines.append(f"- {decision.get('decision_type')}: {decision.get('summary')}")
        else:
            lines.append("- none")
        lines.extend(["", "## Verification"])
        verdict = trace["last_verdict"] or {}
        lines.append(f"- Status: {verdict.get('status', 'none')}")
        lines.append(f"- Summary: {verdict.get('summary', 'none')}")
        lines.extend(["", "## Recovery"])
        recovery = trace["recovery_outcome"] or {}
        lines.append(f"- Summary: {recovery.get('summary', 'none')}")
        lines.extend(["", "## Runtime Evidence"])
        lines.append(f"- Role requests: {len(trace['role_requests'])}")
        lines.append(f"- Role results: {len(trace['role_results'])}")
        lines.append(f"- Model traces: {len(trace['model_trace'])}")
        lines.append(f"- Action traces: {len(trace['action_traces'])}")
        lines.extend(["", "## Timeline"])
        for item in trace.get("timeline", []):
            lines.append(
                f"- {item.get('sequence')}. {item.get('node')} "
                f"[{item.get('status') or 'n/a'}]: {item.get('summary')}"
            )
            if item.get("route"):
                lines.append(f"  route: {item['route']}")
            validation = item.get("validation")
            if isinstance(validation, dict):
                lines.append(
                    "  validation: "
                    f"accepted={validation.get('accepted')} "
                    f"issues={', '.join(validation.get('issues', [])) or 'none'}"
                )
            fallback_decision = item.get("fallback_decision")
            if isinstance(fallback_decision, dict):
                lines.append(f"  fallback: {fallback_decision.get('decision_type')} - {fallback_decision.get('summary')}")
        return "\n".join(lines)

    def dumps_json(self, session: TaskSession, *, action_traces: list[Any] | None = None) -> str:
        return json.dumps(self.export_json(session, action_traces=action_traces), ensure_ascii=False, indent=2)

    def write_json(self, session: TaskSession, path: str | Path, *, action_traces: list[Any] | None = None) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.dumps_json(session, action_traces=action_traces), encoding="utf-8")
        return output_path

    def write_markdown(self, session: TaskSession, path: str | Path, *, action_traces: list[Any] | None = None) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.export_markdown(session, action_traces=action_traces), encoding="utf-8")
        return output_path

    @classmethod
    def _redact(cls, value: Any) -> Any:
        if isinstance(value, dict):
            redacted = {}
            for key, item in value.items():
                if str(key).casefold() in SENSITIVE_KEYS:
                    redacted[key] = "[REDACTED]"
                else:
                    redacted[key] = cls._redact(item)
            return redacted
        if isinstance(value, list):
            return [cls._redact(item) for item in value]
        return value

    @staticmethod
    def _dump_model(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    @staticmethod
    def _build_waypoint_segments(session: TaskSession) -> list[dict[str, Any]]:
        if session.plan is None:
            return []
        behavior_label = session.plan.behavior_label
        segments: list[dict[str, Any]] = []
        for step in session.plan.steps:
            timing = session.waypoint_timings.get(step.step_id, {})
            entered_at_ms = timing.get("entered_at_ms")
            arrived_at_ms = timing.get("arrived_at_ms")
            dwell_ms = (
                arrived_at_ms - entered_at_ms
                if entered_at_ms is not None and arrived_at_ms is not None
                else None
            )
            segments.append(
                {
                    "step_id": step.step_id,
                    "behavior_label": behavior_label,
                    "entered_at_ms": entered_at_ms,
                    "arrived_at_ms": arrived_at_ms,
                    "dwell_ms": dwell_ms,
                }
            )
        return segments

    @staticmethod
    def _build_timeline(trace: dict[str, Any]) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        status_history = trace.get("status_history", [])
        for index, status in enumerate(status_history):
            timeline.append(
                {
                    "sequence": len(timeline) + 1,
                    "node": "status_transition",
                    "role": None,
                    "step_id": None,
                    "status": status,
                    "summary": f"Session entered {status}.",
                    "route": status_history[index + 1] if index + 1 < len(status_history) else None,
                    "evidence_refs": [],
                    "model_trace_refs": [],
                    "action_trace_refs": [],
                }
            )
        action_traces = trace.get("action_traces", [])
        action_by_proposal = {
            item.get("proposal_id"): item
            for item in action_traces
            if isinstance(item, dict) and item.get("proposal_id")
        }
        for result in trace.get("role_results", []):
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            verdict = payload.get("verdict") if isinstance(payload.get("verdict"), dict) else None
            decision = payload.get("step_decision") if isinstance(payload.get("step_decision"), dict) else None
            execution = payload.get("execution_result") if isinstance(payload.get("execution_result"), dict) else None
            node = ExecutionTraceExporter._node_for_role(result.get("role"), decision, verdict, execution)
            evidence_refs = []
            if verdict is not None:
                evidence_refs = [
                    ref.get("evidence_id")
                    for ref in verdict.get("evidence_refs", [])
                    if isinstance(ref, dict) and ref.get("evidence_id")
                ]
            action_refs = []
            proposal_id = None
            if decision is not None and isinstance(decision.get("proposal"), dict):
                proposal_id = decision["proposal"].get("proposal_id")
            if execution is not None:
                proposal_id = execution.get("proposal_id") or proposal_id
            if proposal_id in action_by_proposal:
                action_refs.append(action_by_proposal[proposal_id].get("audit_id"))
            timeline.append(
                {
                    "sequence": len(timeline) + 1,
                    "node": node,
                    "role": result.get("role"),
                    "step_id": result.get("step_id"),
                    "status": verdict.get("status") if verdict is not None else None,
                    "summary": result.get("summary"),
                    "route": result.get("next_role") or result.get("handoff_reason"),
                    "evidence_refs": evidence_refs,
                    "model_trace_refs": payload.get("model_trace_refs", []),
                    "action_trace_refs": [ref for ref in action_refs if ref],
                    "validation": payload.get("validation"),
                    "model_decision": payload.get("model_decision"),
                    "fallback_decision": payload.get("fallback_decision"),
                }
            )
        return timeline

    @staticmethod
    def _memory_highlights(memory_context: dict[str, Any]) -> list[dict[str, Any]]:
        highlights: list[dict[str, Any]] = []
        for key, value in memory_context.items():
            if not key.startswith("memory_context:") or not isinstance(value, dict):
                continue
            for highlight in value.get("highlights", []):
                if not isinstance(highlight, dict):
                    continue
                highlights.append(
                    {
                        "role_scope": value.get("role_scope"),
                        "memory_id": highlight.get("memory_id"),
                        "kind": highlight.get("kind"),
                        "summary": highlight.get("summary"),
                        "score": highlight.get("score"),
                        "confidence_score": highlight.get("confidence_score"),
                        "matched_terms": highlight.get("matched_terms", []),
                        "risk_reason": highlight.get("risk_reason"),
                    }
                )
        return highlights

    @staticmethod
    def _node_for_role(role: str | None, decision: dict | None, verdict: dict | None, execution: dict | None) -> str:
        if role == "planner":
            return "ensure_plan"
        if role == "observer":
            return "observe"
        if role == "step_policy":
            return "decide_step"
        if role == "executor":
            return "dynamic_execute" if execution is not None else "execute"
        if role == "verifier":
            return "verify_recovery" if verdict and verdict.get("matched_check_ids") == ["recovery-effective"] else "verify"
        if role == "recovery":
            return "recover"
        return role or "unknown"


__all__ = ["ExecutionTraceExporter"]
