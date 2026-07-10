from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mobiflow_agent.intake.suite import TestSuiteReport


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


class TestSuiteReportExporter:
    __test__ = False

    def export_json(self, report: TestSuiteReport) -> dict[str, Any]:
        return self._redact(report.model_dump(mode="json"))

    def export_markdown(self, report: TestSuiteReport) -> str:
        data = self.export_json(report)
        header = data.get("suite_name") or data.get("suite_id")
        lines = [
            f"# Test Suite Report: {header}",
            f"- Run: {data['run_id']}",
            f"- Suite: {data['suite_id']}",
            (
                f"- Total: {data['total']}  Passed: {data['passed']}  "
                f"Failed: {data['failed']}  Inconclusive: {data['inconclusive']}  "
                f"Blocked: {data['clarification_blocked']}  Errored: {data['errored']}"
            ),
            f"- Pass rate: {data['pass_rate']:.1%}",
            "",
            "## Summary",
            "| case_id | outcome | verdict | summary | trace |",
            "|---|---|---|---|---|",
        ]
        for row in data.get("results", []):
            verdict = row.get("verdict") or {}
            verdict_status = verdict.get("status") or "-"
            summary = row.get("summary") or "-"
            trace_refs = row.get("trace_refs") or []
            trace = row.get("session_id") or (trace_refs[0] if trace_refs else "-")
            lines.append(
                f"| {row.get('case_id')} | {row.get('outcome')} | "
                f"{verdict_status} | {summary} | {trace} |"
            )
        return "\n".join(lines)

    def dumps_json(self, report: TestSuiteReport) -> str:
        return json.dumps(self.export_json(report), ensure_ascii=False, indent=2)

    def write_json(self, report: TestSuiteReport, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.dumps_json(report), encoding="utf-8")
        return output_path

    def write_markdown(self, report: TestSuiteReport, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.export_markdown(report), encoding="utf-8")
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


__all__ = ["TestSuiteReportExporter"]
