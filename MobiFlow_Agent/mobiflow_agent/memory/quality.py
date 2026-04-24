from __future__ import annotations

"""Memory quality assets and service."""

from enum import Enum

from pydantic import Field, ValidationError

from mobiflow_agent.common.contracts import StrictModel, VerificationStatus

class MemoryCaseQualitySchemaVersion(str, Enum):
    V1 = "v1"

class MemoryCaseQualityDecision(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"

class MemoryCaseQualitySeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"

class MemoryCaseQualityPolicy(StrictModel):
    schema_version: MemoryCaseQualitySchemaVersion = MemoryCaseQualitySchemaVersion.V1
    min_input_summary_length: int = Field(default=8, ge=1)
    max_tags: int = Field(default=16, ge=1)
    require_tags: bool = False
    fail_on_warnings: bool = False

class MemoryCaseQualityIssue(StrictModel):
    severity: MemoryCaseQualitySeverity
    code: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class MemoryCaseNormalizationPreview(StrictModel):
    schema_version: MemoryCaseQualitySchemaVersion = MemoryCaseQualitySchemaVersion.V1
    case_id: str = Field(min_length=1)
    normalized_source: str = Field(min_length=1)
    normalized_category: str = Field(min_length=1)
    normalized_action_name: str = Field(min_length=1)
    normalized_input_summary: str = Field(min_length=1)
    normalized_tags: list[str] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)

class MemoryCaseQualityAssessment(StrictModel):
    schema_version: MemoryCaseQualitySchemaVersion = MemoryCaseQualitySchemaVersion.V1
    case_id: str = Field(min_length=1)
    decision: MemoryCaseQualityDecision
    issue_count: int = Field(ge=0)
    issues: list[MemoryCaseQualityIssue] = Field(default_factory=list)
    normalization_preview: MemoryCaseNormalizationPreview
    summary: str = Field(min_length=1)

class MemoryCaseCatalogQualityEntry(StrictModel):
    case_id: str = Field(min_length=1)
    decision: MemoryCaseQualityDecision
    issue_count: int = Field(ge=0)
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class MemoryCaseCatalogQualityReport(StrictModel):
    schema_version: MemoryCaseQualitySchemaVersion = MemoryCaseQualitySchemaVersion.V1
    catalog_dir: str = Field(min_length=1)
    overall_decision: MemoryCaseQualityDecision
    evaluated_cases: int = Field(ge=0)
    passed_cases: int = Field(ge=0)
    warning_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    entries: list[MemoryCaseCatalogQualityEntry] = Field(default_factory=list)
    issues: list[MemoryCaseQualityIssue] = Field(default_factory=list)
    summary: str = Field(min_length=1)

from mobiflow_agent.memory.models import TaskMemoryPolicy, TaskMemoryRecord
from mobiflow_agent.platform.types import RecoveryGuidance

class MemoryCaseQualityService:
    def __init__(
        self,
        *,
        persistence_service=None,
    ) -> None:
        if persistence_service is None:
            from mobiflow_agent.memory.catalog import MemoryCasePersistenceService

            persistence_service = MemoryCasePersistenceService()
        self._persistence_service = persistence_service

    def preview_normalization(
        self,
        case: RecoveryMemoryCase,
        *,
        policy: MemoryCaseQualityPolicy | None = None,
    ) -> MemoryCaseNormalizationPreview:
        del policy
        normalized_source = case.source.strip()
        normalized_category = case.category.strip()
        normalized_action_name = case.action_name.strip()
        normalized_input_summary = case.input_summary.strip()
        from mobiflow_agent.memory.case import MemoryCaseRetrievalService

        normalized_tags = MemoryCaseRetrievalService._normalize_tags(case.tags)

        changed_fields: list[str] = []
        if normalized_source != case.source:
            changed_fields.append("source")
        if normalized_category != case.category:
            changed_fields.append("category")
        if normalized_action_name != case.action_name:
            changed_fields.append("action_name")
        if normalized_input_summary != case.input_summary:
            changed_fields.append("input_summary")
        if normalized_tags != case.tags:
            changed_fields.append("tags")

        summary = (
            f"Memory case {case.case_id} normalization changes {len(changed_fields)} field(s)."
            if changed_fields
            else f"Memory case {case.case_id} does not require normalization changes."
        )
        return MemoryCaseNormalizationPreview(
            case_id=case.case_id,
            normalized_source=normalized_source,
            normalized_category=normalized_category,
            normalized_action_name=normalized_action_name,
            normalized_input_summary=normalized_input_summary,
            normalized_tags=normalized_tags,
            changed_fields=changed_fields,
            summary=summary,
        )

    def assess_case(
        self,
        case: RecoveryMemoryCase,
        *,
        policy: MemoryCaseQualityPolicy | None = None,
    ) -> MemoryCaseQualityAssessment:
        resolved_policy = policy or MemoryCaseQualityPolicy()
        preview = self.preview_normalization(case, policy=resolved_policy)
        issues: list[MemoryCaseQualityIssue] = []

        issues.extend(self._normalization_warnings(case, preview, resolved_policy))
        issues.extend(self._consistency_issues(case))

        decision = self._decision_for_issues(issues, resolved_policy)
        return MemoryCaseQualityAssessment(
            case_id=case.case_id,
            decision=decision,
            issue_count=len(issues),
            issues=issues,
            normalization_preview=preview,
            summary=self._assessment_summary(case.case_id, decision, len(issues)),
        )

    def assess_catalog(
        self,
        catalog_dir: str,
        *,
        policy: MemoryCaseQualityPolicy | None = None,
    ) -> MemoryCaseCatalogQualityReport:
        resolved_policy = policy or MemoryCaseQualityPolicy()
        catalog = self._persistence_service.list_catalog(catalog_dir)
        if not catalog.entries:
            return MemoryCaseCatalogQualityReport(
                catalog_dir=catalog.catalog_dir,
                overall_decision=MemoryCaseQualityDecision.FAILED,
                evaluated_cases=0,
                passed_cases=0,
                warning_cases=0,
                failed_cases=0,
                entries=[],
                issues=[],
                summary=f"Memory catalog {catalog.catalog_dir} has no memory evidence to assess.",
            )

        entries: list[MemoryCaseCatalogQualityEntry] = []
        issues: list[MemoryCaseQualityIssue] = []
        passed_cases = 0
        warning_cases = 0
        failed_cases = 0

        for catalog_entry in catalog.entries:
            case = self._persistence_service.load_case(catalog_entry.path)
            assessment = self.assess_case(case, policy=resolved_policy)
            issues.extend(assessment.issues)
            entries.append(
                MemoryCaseCatalogQualityEntry(
                    case_id=assessment.case_id,
                    decision=assessment.decision,
                    issue_count=assessment.issue_count,
                    path=catalog_entry.path,
                    summary=assessment.summary,
                )
            )
            if assessment.decision == MemoryCaseQualityDecision.PASSED:
                passed_cases += 1
            elif assessment.decision == MemoryCaseQualityDecision.WARNING:
                warning_cases += 1
            else:
                failed_cases += 1

        overall_decision = self._overall_decision(
            failed_cases=failed_cases,
            warning_cases=warning_cases,
        )
        return MemoryCaseCatalogQualityReport(
            catalog_dir=catalog.catalog_dir,
            overall_decision=overall_decision,
            evaluated_cases=len(entries),
            passed_cases=passed_cases,
            warning_cases=warning_cases,
            failed_cases=failed_cases,
            entries=entries,
            issues=issues,
            summary=self._catalog_summary(
                catalog_dir=catalog.catalog_dir,
                decision=overall_decision,
                evaluated_cases=len(entries),
                issue_count=len(issues),
            ),
        )

    def _normalization_warnings(
        self,
        case: RecoveryMemoryCase,
        preview: MemoryCaseNormalizationPreview,
        policy: MemoryCaseQualityPolicy,
    ) -> list[MemoryCaseQualityIssue]:
        issues: list[MemoryCaseQualityIssue] = []
        for field_name in ("source", "category", "action_name", "input_summary"):
            if field_name in preview.changed_fields:
                issues.append(
                    self._issue(
                        severity=MemoryCaseQualitySeverity.WARNING,
                        case_id=case.case_id,
                        code=f"{field_name}_normalized",
                        field_path=field_name,
                        summary=f"Memory case {case.case_id} requires normalization for {field_name}.",
                    )
                )

        if "tags" in preview.changed_fields:
            issues.append(
                self._issue(
                    severity=MemoryCaseQualitySeverity.WARNING,
                    case_id=case.case_id,
                    code="tags_normalized",
                    field_path="tags",
                    summary=f"Memory case {case.case_id} has tags that require trimming or deduplication.",
                )
            )

        if len(preview.normalized_input_summary) < policy.min_input_summary_length:
            issues.append(
                self._issue(
                    severity=MemoryCaseQualitySeverity.WARNING,
                    case_id=case.case_id,
                    code="input_summary_too_short",
                    field_path="input_summary",
                    summary=(
                        f"Memory case {case.case_id} input_summary is shorter than "
                        f"{policy.min_input_summary_length} characters after normalization."
                    ),
                )
            )

        if len(preview.normalized_tags) > policy.max_tags:
            issues.append(
                self._issue(
                    severity=MemoryCaseQualitySeverity.WARNING,
                    case_id=case.case_id,
                    code="too_many_tags",
                    field_path="tags",
                    summary=(
                        f"Memory case {case.case_id} has {len(preview.normalized_tags)} normalized tags, "
                        f"which exceeds the policy limit {policy.max_tags}."
                    ),
                )
            )

        if policy.require_tags and not preview.normalized_tags:
            issues.append(
                self._issue(
                    severity=MemoryCaseQualitySeverity.WARNING,
                    case_id=case.case_id,
                    code="tags_required",
                    field_path="tags",
                    summary=f"Memory case {case.case_id} must include at least one tag under the current policy.",
                )
            )

        return issues

    def _consistency_issues(self, case: RecoveryMemoryCase) -> list[MemoryCaseQualityIssue]:
        from mobiflow_agent.memory.case import MemoryCaseRetrievalService

        issues: list[MemoryCaseQualityIssue] = []
        replay_case = case.replay_case
        if replay_case.execution.action_name != case.action_name:
            issues.append(
                self._issue(
                    severity=MemoryCaseQualitySeverity.ERROR,
                    case_id=case.case_id,
                    code="action_name_mismatch",
                    field_path="action_name",
                    summary=(
                        f"Memory case {case.case_id} action_name does not match replay_case.execution.action_name."
                    ),
                )
            )
        if replay_case.harness_response.decision != case.decision:
            issues.append(
                self._issue(
                    severity=MemoryCaseQualitySeverity.ERROR,
                    case_id=case.case_id,
                    code="decision_mismatch",
                    field_path="decision",
                    summary=(
                        f"Memory case {case.case_id} decision does not match replay_case.harness_response.decision."
                    ),
                )
            )

        replay_verdict_status = MemoryCaseRetrievalService._extract_verdict_status(
            replay_case.harness_response
        )
        if replay_verdict_status != case.verdict_status:
            issues.append(
                self._issue(
                    severity=MemoryCaseQualitySeverity.ERROR,
                    case_id=case.case_id,
                    code="verdict_status_mismatch",
                    field_path="verdict_status",
                    summary=(
                        f"Memory case {case.case_id} verdict_status does not match replay_case "
                        "harness verdict status."
                    ),
                )
            )

        if case.eval_case is not None and case.eval_case.replay_case.case_id != replay_case.case_id:
            issues.append(
                self._issue(
                    severity=MemoryCaseQualitySeverity.ERROR,
                    case_id=case.case_id,
                    code="eval_replay_case_mismatch",
                    field_path="eval_case.replay_case.case_id",
                    summary=(
                        f"Memory case {case.case_id} eval_case does not point to the same replay case as "
                        "the canonical replay_case field."
                    ),
                )
            )
        return issues

    @staticmethod
    def _issue(
        *,
        severity: MemoryCaseQualitySeverity,
        case_id: str,
        code: str,
        field_path: str,
        summary: str,
    ) -> MemoryCaseQualityIssue:
        return MemoryCaseQualityIssue(
            severity=severity,
            code=code,
            case_id=case_id,
            field_path=field_path,
            summary=summary,
        )

    @staticmethod
    def _decision_for_issues(
        issues: list[MemoryCaseQualityIssue],
        policy: MemoryCaseQualityPolicy,
    ) -> MemoryCaseQualityDecision:
        has_errors = any(issue.severity == MemoryCaseQualitySeverity.ERROR for issue in issues)
        if has_errors:
            return MemoryCaseQualityDecision.FAILED
        if issues:
            if policy.fail_on_warnings:
                return MemoryCaseQualityDecision.FAILED
            return MemoryCaseQualityDecision.WARNING
        return MemoryCaseQualityDecision.PASSED

    @staticmethod
    def _overall_decision(
        *,
        failed_cases: int,
        warning_cases: int,
    ) -> MemoryCaseQualityDecision:
        if failed_cases > 0:
            return MemoryCaseQualityDecision.FAILED
        if warning_cases > 0:
            return MemoryCaseQualityDecision.WARNING
        return MemoryCaseQualityDecision.PASSED

    @staticmethod
    def _assessment_summary(
        case_id: str,
        decision: MemoryCaseQualityDecision,
        issue_count: int,
    ) -> str:
        if issue_count == 0:
            return f"Memory case {case_id} passed quality assessment with no issues."
        return (
            f"Memory case {case_id} {decision.value} quality assessment with "
            f"{issue_count} issue(s)."
        )

    @staticmethod
    def _catalog_summary(
        *,
        catalog_dir: str,
        decision: MemoryCaseQualityDecision,
        evaluated_cases: int,
        issue_count: int,
    ) -> str:
        return (
            f"Memory catalog {catalog_dir} {decision.value} quality assessment across "
            f"{evaluated_cases} case(s) with {issue_count} issue(s)."
        )


class TaskMemoryQualityDecision(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class TaskMemoryQualitySeverity(str, Enum):
    WARNING = "warning"
    ERROR = "error"


class TaskMemoryQualityPolicy(StrictModel):
    max_tags: int = Field(default=16, ge=1)
    max_payload_chars: int = Field(default=4000, ge=256)
    allow_unknown_writeback: bool = False
    require_evidence_for_writeback: bool = True
    fail_on_warnings: bool = False


class TaskMemoryQualityIssue(StrictModel):
    severity: TaskMemoryQualitySeverity
    code: str = Field(min_length=1)
    memory_id: str = Field(min_length=1)
    field_path: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class TaskMemoryQualityAssessment(StrictModel):
    memory_id: str = Field(min_length=1)
    decision: TaskMemoryQualityDecision
    issue_count: int = Field(ge=0)
    issues: list[TaskMemoryQualityIssue] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryQualityReport(StrictModel):
    evaluated_records: int = Field(ge=0)
    passed_records: int = Field(ge=0)
    warning_records: int = Field(ge=0)
    failed_records: int = Field(ge=0)
    assessments: list[TaskMemoryQualityAssessment] = Field(default_factory=list)
    issues: list[TaskMemoryQualityIssue] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryQualityService:
    def assess_record(
        self,
        record: TaskMemoryRecord,
        *,
        policy: TaskMemoryQualityPolicy | TaskMemoryPolicy | None = None,
    ) -> TaskMemoryQualityAssessment:
        resolved_policy = self._resolve_policy(policy)
        issues: list[TaskMemoryQualityIssue] = []

        if not record.goal.strip():
            issues.append(self._issue(record, "goal_missing", "goal", "Task memory record must include a goal."))
        if not record.summary.strip():
            issues.append(self._issue(record, "summary_missing", "summary", "Task memory record must include a summary."))
        if record.kind.value.endswith("pattern") and not record.role_scope:
            issues.append(self._issue(record, "role_scope_missing", "role_scope", "Pattern memory must be scoped to a role."))
        if not record.proposal_fingerprint:
            issues.append(self._issue(record, "fingerprint_missing", "proposal_fingerprint", "Task memory record must include a stable fingerprint."))
        if len(record.tags) > resolved_policy.max_tags:
            issues.append(
                self._issue(
                    record,
                    "too_many_tags",
                    "tags",
                    f"Task memory record has {len(record.tags)} tags, exceeding {resolved_policy.max_tags}.",
                    severity=TaskMemoryQualitySeverity.WARNING,
                )
            )
        if self._payload_chars(record) > resolved_policy.max_payload_chars:
            issues.append(
                self._issue(
                    record,
                    "payload_too_large",
                    "content_payload",
                    f"Task memory payload exceeds {resolved_policy.max_payload_chars} character(s).",
                    severity=TaskMemoryQualitySeverity.WARNING,
                )
            )

        if record.verdict_status == VerificationStatus.VERIFIED_UNKNOWN and not resolved_policy.allow_unknown_writeback:
            issues.append(
                self._issue(
                    record,
                    "unknown_verdict_rejected",
                    "verdict_status",
                    "VERIFIED_UNKNOWN memory is not eligible for default writeback.",
                )
            )
        if (
            record.verdict_status in {
                VerificationStatus.VERIFIED_SUCCESS,
                VerificationStatus.VERIFIED_FAILED,
                VerificationStatus.BLOCKED,
            }
            and resolved_policy.require_evidence_for_writeback
            and not record.evidence_ref_ids
            and not self._has_audit_trace(record)
        ):
            issues.append(
                self._issue(
                    record,
                    "writeback_evidence_missing",
                    "evidence_ref_ids",
                    "Stable memory writeback requires evidence refs or an auditable action trace.",
                )
            )
        if record.verdict_status in {VerificationStatus.VERIFIED_FAILED, VerificationStatus.BLOCKED}:
            if not record.blocked_reason and not self._has_failure_summary(record):
                issues.append(
                    self._issue(
                        record,
                        "failure_reason_missing",
                        "blocked_reason",
                        "Failed or blocked memory requires blocked_reason or a clear failure summary.",
                    )
                )
        if "recovery_guidance" in record.content_payload:
            guidance_payload = record.content_payload.get("recovery_guidance")
            if guidance_payload is not None:
                try:
                    RecoveryGuidance.model_validate(guidance_payload)
                except ValidationError:
                    issues.append(
                        self._issue(
                            record,
                            "invalid_recovery_guidance",
                            "content_payload.recovery_guidance",
                            "Recovery guidance payload must match the RecoveryGuidance schema.",
                        )
                    )

        decision = self._decision_for_issues(issues, resolved_policy)
        return TaskMemoryQualityAssessment(
            memory_id=record.memory_id,
            decision=decision,
            issue_count=len(issues),
            issues=issues,
            summary=self._assessment_summary(record.memory_id, decision, len(issues)),
        )

    def assess_records(
        self,
        records: list[TaskMemoryRecord],
        *,
        policy: TaskMemoryQualityPolicy | TaskMemoryPolicy | None = None,
    ) -> TaskMemoryQualityReport:
        assessments = [self.assess_record(record, policy=policy) for record in records]
        passed = sum(1 for item in assessments if item.decision == TaskMemoryQualityDecision.PASSED)
        warning = sum(1 for item in assessments if item.decision == TaskMemoryQualityDecision.WARNING)
        failed = sum(1 for item in assessments if item.decision == TaskMemoryQualityDecision.FAILED)
        issues = [issue for assessment in assessments for issue in assessment.issues]
        return TaskMemoryQualityReport(
            evaluated_records=len(records),
            passed_records=passed,
            warning_records=warning,
            failed_records=failed,
            assessments=assessments,
            issues=issues,
            summary=(
                f"Assessed {len(records)} task memory record(s): "
                f"passed={passed}, warning={warning}, failed={failed}."
            ),
        )

    @staticmethod
    def _resolve_policy(policy: TaskMemoryQualityPolicy | TaskMemoryPolicy | None) -> TaskMemoryQualityPolicy:
        if policy is None:
            return TaskMemoryQualityPolicy()
        if isinstance(policy, TaskMemoryQualityPolicy):
            return policy
        return TaskMemoryQualityPolicy(
            max_payload_chars=policy.max_payload_chars,
            allow_unknown_writeback=policy.allow_unknown_writeback,
            require_evidence_for_writeback=policy.require_evidence_for_writeback,
        )

    @staticmethod
    def _issue(
        record: TaskMemoryRecord,
        code: str,
        field_path: str,
        summary: str,
        *,
        severity: TaskMemoryQualitySeverity = TaskMemoryQualitySeverity.ERROR,
    ) -> TaskMemoryQualityIssue:
        return TaskMemoryQualityIssue(
            severity=severity,
            code=code,
            memory_id=record.memory_id,
            field_path=field_path,
            summary=summary,
        )

    @staticmethod
    def _decision_for_issues(
        issues: list[TaskMemoryQualityIssue],
        policy: TaskMemoryQualityPolicy,
    ) -> TaskMemoryQualityDecision:
        if any(issue.severity == TaskMemoryQualitySeverity.ERROR for issue in issues):
            return TaskMemoryQualityDecision.FAILED
        if issues:
            return TaskMemoryQualityDecision.FAILED if policy.fail_on_warnings else TaskMemoryQualityDecision.WARNING
        return TaskMemoryQualityDecision.PASSED

    @staticmethod
    def _payload_chars(record: TaskMemoryRecord) -> int:
        return len(str(record.content_payload))

    @staticmethod
    def _has_audit_trace(record: TaskMemoryRecord) -> bool:
        audit_id = record.content_payload.get("audit_id")
        action_trace = record.content_payload.get("action_trace")
        return bool(audit_id or action_trace)

    @staticmethod
    def _has_failure_summary(record: TaskMemoryRecord) -> bool:
        text = f"{record.summary} {record.content_payload.get('last_verdict_summary', '')}".casefold()
        return any(term in text for term in ("blocked", "failed", "failure", "error"))

    @staticmethod
    def _assessment_summary(
        memory_id: str,
        decision: TaskMemoryQualityDecision,
        issue_count: int,
    ) -> str:
        if issue_count == 0:
            return f"Task memory record {memory_id} passed quality assessment with no issues."
        return f"Task memory record {memory_id} {decision.value} quality assessment with {issue_count} issue(s)."
