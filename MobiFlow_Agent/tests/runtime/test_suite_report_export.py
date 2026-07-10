from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.intake.suite import (
    SuiteCaseOutcome,
    TestRunResult,
    TestSuiteReport,
)
from mobiflow_agent.runtime.suite_report_export import TestSuiteReportExporter
from mobiflow_agent.task.plan import TaskStatus


def _passed_result() -> TestRunResult:
    verdict = VerificationVerdict(
        verdict_id="verdict:success",
        status=VerificationStatus.VERIFIED_SUCCESS,
        summary="home screen visible",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        evidence_refs=[
            EvidenceRef(
                evidence_id="snapshot:task:task-1",
                kind=EvidenceKind.PLATFORM_SNAPSHOT,
                summary="snapshot",
                locator="loc-1",
            )
        ],
    )
    return TestRunResult(
        run_id="suite-run:r1",
        case_id="checkout-01",
        outcome=SuiteCaseOutcome.PASSED,
        verdict=verdict,
        session_id="task-session:sess-1",
        session_status=TaskStatus.COMPLETED,
        trace_refs=["trace:1"],
    )


def _blocked_result() -> TestRunResult:
    return TestRunResult(
        run_id="suite-run:r1",
        case_id="bad-prose-03",
        outcome=SuiteCaseOutcome.CLARIFICATION_BLOCKED,
        summary="What is the expected result?",
    )


def _report() -> TestSuiteReport:
    return TestSuiteReport(
        run_id="suite-run:r1",
        suite_id="suite-1",
        suite_name="regression",
        total=2,
        passed=1,
        failed=0,
        inconclusive=0,
        clarification_blocked=1,
        errored=0,
        pass_rate=0.5,
        results=[_passed_result(), _blocked_result()],
        generated_at_ms=123,
    )


def test_export_json_returns_redacted_dict() -> None:
    exporter = TestSuiteReportExporter()
    payload = exporter.export_json(_report())
    assert payload["run_id"] == "suite-run:r1"
    assert payload["total"] == 2
    assert len(payload["results"]) == 2
    # Field-mask the uuid-based ids (R5) rather than assert full golden.
    assert payload["results"][0]["session_id"].startswith("task-session:")
    assert payload["results"][0]["verdict"]["verdict_id"].startswith("verdict:")


def test_export_json_redacts_sensitive_keys() -> None:
    # TestSuiteReport/TestRunResult are StrictModel (extra="forbid"), so sensitive keys
    # cannot be injected as top-level fields on the real model shape.  The honest test is
    # to exercise _redact directly: it is a pure classmethod on a plain dict.
    redacted = TestSuiteReportExporter._redact(
        {
            "token": "sk-secret",
            "safe": "keep-me",
            "nested": {
                "api_key": "key-value",
                "password": "hunter2",
                "normal": "visible",
            },
            "list_field": [
                {"authorization": "Bearer abc", "data": "ok"},
            ],
        }
    )
    # Sensitive keys are masked at every nesting level.
    assert redacted["token"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["list_field"][0]["authorization"] == "[REDACTED]"
    # Non-sensitive keys are preserved unchanged.
    assert redacted["safe"] == "keep-me"
    assert redacted["nested"]["normal"] == "visible"
    assert redacted["list_field"][0]["data"] == "ok"
    # Secret values must not appear anywhere in the output.
    import json
    dumped = json.dumps(redacted)
    assert "sk-secret" not in dumped
    assert "key-value" not in dumped
    assert "hunter2" not in dumped
    assert "Bearer abc" not in dumped


def test_export_markdown_builds_from_redacted_dict_with_masked_ids() -> None:
    exporter = TestSuiteReportExporter()
    markdown = exporter.export_markdown(_report())
    assert "# Test Suite Report: regression" in markdown
    assert "- Run: suite-run:r1" in markdown
    assert "Passed: 1" in markdown
    assert "Pass rate: 50.0%" in markdown
    # Row rendering (R5: assert stable columns, not the uuid-bearing trace cell verbatim).
    assert "| checkout-01 | passed | verified_success |" in markdown
    assert "| bad-prose-03 | clarification_blocked | - | What is the expected result? | - |" in markdown


def test_write_json_and_markdown(tmp_path) -> None:
    exporter = TestSuiteReportExporter()
    json_path = exporter.write_json(_report(), tmp_path / "report.json")
    md_path = exporter.write_markdown(_report(), tmp_path / "report.md")
    assert json_path.exists()
    assert md_path.exists()
    assert "Test Suite Report" in md_path.read_text(encoding="utf-8")
