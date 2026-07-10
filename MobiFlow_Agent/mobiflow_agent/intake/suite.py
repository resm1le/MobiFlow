from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import StrictModel, VerificationVerdict
from mobiflow_agent.task.plan import TaskStatus


class SuiteCaseOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    CLARIFICATION_BLOCKED = "clarification_blocked"
    ERROR = "error"


class SuiteCaseInput(StrictModel):
    case_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    platform_context: dict[str, Any] | None = None
    confirmed: bool = False


class TestSuite(StrictModel):
    __test__ = False

    suite_id: str = Field(min_length=1)
    name: str | None = None
    cases: list[SuiteCaseInput] = Field(min_length=1)


class TestRunResult(StrictModel):
    __test__ = False

    run_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    outcome: SuiteCaseOutcome
    verdict: VerificationVerdict | None = None
    session_id: str | None = None
    session_status: TaskStatus | None = None
    summary: str | None = None
    trace_refs: list[str] = Field(default_factory=list)


class TestSuiteReport(StrictModel):
    __test__ = False

    run_id: str = Field(min_length=1)
    suite_id: str = Field(min_length=1)
    suite_name: str | None = None
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    inconclusive: int = Field(ge=0)
    clarification_blocked: int = Field(ge=0)
    errored: int = Field(ge=0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    results: list[TestRunResult] = Field(default_factory=list)
    generated_at_ms: int | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "TestSuiteReport":
        tallied = (
            self.passed
            + self.failed
            + self.inconclusive
            + self.clarification_blocked
            + self.errored
        )
        if tallied != self.total:
            raise ValueError(
                "TestSuiteReport counts must sum to total: "
                f"{tallied} != {self.total}."
            )
        if self.total == 0 and self.pass_rate != 0.0:
            raise ValueError("TestSuiteReport pass_rate must be 0.0 when total is 0.")
        return self


__all__ = [
    "SuiteCaseInput",
    "SuiteCaseOutcome",
    "TestRunResult",
    "TestSuite",
    "TestSuiteReport",
]
