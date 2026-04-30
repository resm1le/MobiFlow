from __future__ import annotations

import json
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
            "plan": None if session.plan is None else self._redact(session.plan.model_dump(mode="python")),
            "current_step": None
            if session.current_step is None
            else self._redact(session.current_step.model_dump(mode="python")),
            "step_decisions": [
                self._redact(decision.model_dump(mode="python")) for decision in session.step_decisions
            ],
            "role_requests": [
                self._redact(request.model_dump(mode="python")) for request in session.role_requests
            ],
            "role_results": [
                self._redact(result.model_dump(mode="python")) for result in session.role_results
            ],
            "last_observation": None
            if session.last_observation is None
            else self._redact(session.last_observation.model_dump(mode="python")),
            "last_execution_result": None
            if session.last_execution_result is None
            else self._redact(session.last_execution_result.model_dump(mode="python")),
            "pending_execution": None
            if session.pending_execution is None
            else self._redact(session.pending_execution.model_dump(mode="python")),
            "last_verdict": None if session.last_verdict is None else self._redact(session.last_verdict.model_dump(mode="python")),
            "recovery_outcome": None
            if session.recovery_outcome is None
            else self._redact(session.recovery_outcome.model_dump(mode="python")),
            "memory_context_keys": sorted(session.memory_context),
            "memory_writeback": self._redact(session.memory_context.get("memory_writeback:last")),
            "model_trace": [
                self._redact(trace.model_dump(mode="python")) for trace in session.model_trace
            ],
            "action_traces": [self._redact(self._dump_model(trace)) for trace in action_traces or []],
        }
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
        return "\n".join(lines)

    def dumps_json(self, session: TaskSession, *, action_traces: list[Any] | None = None) -> str:
        return json.dumps(self.export_json(session, action_traces=action_traces), ensure_ascii=False, indent=2)

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
            return value.model_dump(mode="python")
        return value


__all__ = ["ExecutionTraceExporter"]
