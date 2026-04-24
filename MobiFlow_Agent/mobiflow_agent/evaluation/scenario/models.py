from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import EvidenceKind, StrictModel, VerificationStatus
from mobiflow_agent.platform.simulation import SimulatedActionTrace, SimulatedMobileScenario
from mobiflow_agent.runtime.harness import TaskHarnessRequest, TaskHarnessResponse, TaskHarnessStatus


class ScenarioEvaluationSchemaVersion(str, Enum):
    V1 = "v1"


class ScenarioExpectation(StrictModel):
    expected_final_status: TaskHarnessStatus | None = None
    expected_verification_status: VerificationStatus | None = None
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_evidence_kinds: list[EvidenceKind] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    expect_approval_pause: bool = False
    expect_recovery_path: bool = False


class ScenarioEvaluationCase(StrictModel):
    schema_version: ScenarioEvaluationSchemaVersion = ScenarioEvaluationSchemaVersion.V1
    scenario_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    platform_scenario: SimulatedMobileScenario
    requests: list[TaskHarnessRequest] = Field(default_factory=list)
    expectation: ScenarioExpectation
    approval_decisions: dict[int, bool] = Field(default_factory=dict)
    allow_recovery: bool = True
    heartbeat_ticks: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_requests(self) -> "ScenarioEvaluationCase":
        if not self.requests:
            raise ValueError("ScenarioEvaluationCase requires at least one harness request.")
        for index in self.approval_decisions:
            if index < 0 or index >= len(self.requests):
                raise ValueError(f"approval_decisions references unknown request index {index}.")
        return self


class ScenarioEvaluationResult(StrictModel):
    schema_version: ScenarioEvaluationSchemaVersion = ScenarioEvaluationSchemaVersion.V1
    scenario_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    responses: list[TaskHarnessResponse] = Field(default_factory=list)
    final_response: TaskHarnessResponse
    action_traces: list[SimulatedActionTrace] = Field(default_factory=list)
    matched: bool
    failures: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class ScenarioEvaluationReport(StrictModel):
    schema_version: ScenarioEvaluationSchemaVersion = ScenarioEvaluationSchemaVersion.V1
    total_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    mismatched_cases: int = Field(ge=0)
    results: list[ScenarioEvaluationResult] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class ScenarioMemoryComparisonOutcome(str, Enum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"


class ScenarioMemoryComparisonResult(StrictModel):
    schema_version: ScenarioEvaluationSchemaVersion = ScenarioEvaluationSchemaVersion.V1
    scenario_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    memory_off_result: ScenarioEvaluationResult
    memory_on_result: ScenarioEvaluationResult
    outcome: ScenarioMemoryComparisonOutcome
    improved: bool
    regressed: bool
    unchanged: bool
    memory_hit_count: int = Field(ge=0)
    active_hit_count: int = Field(default=0, ge=0)
    writeback_count: int = Field(ge=0)
    quality_rejection_count: int = Field(ge=0)
    quarantined_count: int = Field(default=0, ge=0)
    expired_count: int = Field(default=0, ge=0)
    superseded_count: int = Field(default=0, ge=0)
    summary: str = Field(min_length=1)


class ScenarioMemoryComparisonReport(StrictModel):
    schema_version: ScenarioEvaluationSchemaVersion = ScenarioEvaluationSchemaVersion.V1
    total_cases: int = Field(ge=0)
    improved_cases: int = Field(ge=0)
    regressed_cases: int = Field(ge=0)
    unchanged_cases: int = Field(ge=0)
    results: list[ScenarioMemoryComparisonResult] = Field(default_factory=list)
    summary: str = Field(min_length=1)


__all__ = [
    "ScenarioEvaluationCase",
    "ScenarioEvaluationReport",
    "ScenarioEvaluationResult",
    "ScenarioEvaluationSchemaVersion",
    "ScenarioExpectation",
    "ScenarioMemoryComparisonOutcome",
    "ScenarioMemoryComparisonReport",
    "ScenarioMemoryComparisonResult",
]
