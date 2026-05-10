from __future__ import annotations

from typing import Any

import pytest

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, ObservationView
from mobiflow_agent.platform.evidence import (
    ATTEMPT_DIAGNOSIS_FACT_ID,
    RUN_ARTIFACTS_FACT_ID,
    RUN_GOVERNANCE_FACT_ID,
    RUN_LINEAGE_FACT_ID,
)
from mobiflow_agent.platform.adapter import (
    FakePlatformAdapter,
    HttpPlatformAdapter,
    McpPlatformAdapter,
    PlatformAdapterError,
    create_platform_adapter,
)
from mobiflow_agent.platform.types import (
    FailureCategory,
    GovernedActionState,
    RetryRecommendation,
    SuggestedNextAction,
    ToolRiskLevel,
)
from mobiflow_agent.runtime.state import CallerContext


class StubTransport:
    def __init__(self, responses: dict[tuple[str, str], list[dict[str, Any]]] | None = None):
        self.responses = responses or {}
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []

    def request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.requests.append((method, path, payload))
        key = (method, path)
        if key not in self.responses or not self.responses[key]:
            raise AssertionError(f"Unexpected request: {method} {path}")
        return self.responses[key].pop(0)

    def download_bytes(self, path: str) -> bytes:
        raise AssertionError(f"Unexpected binary download: {path}")


class StubMcpTransport:
    def __init__(self, responses: dict[str, list[dict[str, Any]]] | None = None):
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, params))
        if method not in self.responses or not self.responses[method]:
            raise AssertionError(f"Unexpected MCP call: {method}")
        return self.responses[method].pop(0)


def test_get_tool_catalog_maps_catalog_items() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("GET", "/tools/catalog"): [
                    {
                        "tools": [
                            {
                                "name": "cancel_run",
                                "title": "Cancel Run",
                                "description": "Cancel a blocked run.",
                                "toolKind": "action",
                                "riskLevel": "execution",
                                "inputSchema": {
                                    "type": "object",
                                    "required": ["runId"],
                                },
                                "semanticTags": ["run", "governance"],
                                "governance": {
                                    "requiresApproval": True,
                                    "confirmationMode": "always",
                                },
                            }
                        ]
                    }
                ]
            }
        )
    )

    catalog = adapter.get_tool_catalog()

    assert len(catalog) == 1
    assert catalog[0].name == "cancel_run"
    assert catalog[0].requires_approval is True
    assert catalog[0].risk_level == ToolRiskLevel.EXECUTION
    assert catalog[0].confirmation_mode == "always"
    assert catalog[0].input_schema["required"] == ["runId"]


def test_mcp_get_tool_catalog_maps_mcp_tools() -> None:
    adapter = McpPlatformAdapter(
        transport=StubMcpTransport(
            {
                "tools/list": [
                    {
                        "tools": [
                            {
                                "name": "cancel_run",
                                "title": "Cancel Run",
                                "description": "Cancel a blocked run.",
                                "inputSchema": {"type": "object", "required": ["runId"]},
                                "_meta": {
                                    "mobiflow/toolKind": "side_effect",
                                    "mobiflow/riskLevel": "EXECUTION",
                                    "mobiflow/governance": {
                                        "requiresApproval": True,
                                        "confirmationMode": "explicit",
                                    },
                                    "mobiflow/semanticTags": ["run", "governed"],
                                },
                            }
                        ]
                    }
                ]
            }
        )
    )

    catalog = adapter.get_tool_catalog()

    assert len(catalog) == 1
    assert catalog[0].name == "cancel_run"
    assert catalog[0].risk_level == ToolRiskLevel.EXECUTION
    assert catalog[0].requires_approval is True
    assert catalog[0].semantic_tags == ["run", "governed"]


def test_mcp_submit_execution_proposal_maps_completed_response() -> None:
    transport = StubMcpTransport(
        {
            "tools/call": [
                {
                    "structuredContent": {
                        "tool": "propose_governed_action",
                        "status": "completed",
                        "result": {"status": "accepted"},
                        "warnings": ["policy logged"],
                        "audit": {"auditId": "audit-1", "riskLevel": "execution"},
                        "entityRefs": {"proposalId": "proposal-1", "runId": "run-1"},
                    },
                    "isError": False,
                }
            ]
        }
    )
    adapter = McpPlatformAdapter(transport=transport)

    result = adapter.submit_execution_proposal(
        proposal=ExecutionProposal(
            proposal_id="proposal-1",
            action_tool_name="cancel_run",
            arguments={"runId": "run-1"},
            target_kind=EntityKind.RUN,
            target_id="run-1",
            rationale="Cancel blocked run.",
        ),
        caller_context=CallerContext(
            session_id="session-1",
            agent_task_id="task-1",
            turn_id="turn-1",
            step_id="step-1",
        ),
    )

    assert result.state == GovernedActionState.EXECUTED
    assert result.audit is not None and result.audit.audit_id == "audit-1"
    assert result.entity_refs is not None and result.entity_refs.run_id == "run-1"
    assert transport.calls[0][0] == "tools/call"
    assert transport.calls[0][1]["name"] == "propose_governed_action"


def test_mcp_submit_execution_proposal_maps_approval_required_response() -> None:
    adapter = McpPlatformAdapter(
        transport=StubMcpTransport(
            {
                "tools/call": [
                    {
                        "structuredContent": {
                            "tool": "propose_governed_action",
                            "status": "approval_required",
                            "audit": {"auditId": "audit-2", "riskLevel": "execution"},
                            "entityRefs": {"proposalId": "proposal-2", "runId": "run-2"},
                            "confirmation": {
                                "confirmationId": "confirm-2",
                                "summary": "Approve cancelling run-2",
                                "expiresAt": 1710000000000,
                            },
                        },
                        "isError": False,
                    }
                ]
            }
        )
    )

    result = adapter.submit_execution_proposal(
        proposal=ExecutionProposal(
            proposal_id="proposal-2",
            action_tool_name="cancel_run",
            arguments={"runId": "run-2"},
            target_kind=EntityKind.RUN,
            target_id="run-2",
            rationale="Cancel blocked run.",
        ),
        caller_context=CallerContext(
            session_id="session-1",
            agent_task_id="task-1",
            turn_id="turn-1",
            step_id="step-1",
        ),
    )

    assert result.state == GovernedActionState.APPROVAL_REQUIRED
    assert result.confirmation_id == "confirm-2"
    assert result.confirmation_summary == "Approve cancelling run-2"


def test_mcp_resolve_approval_calls_confirmation_tool() -> None:
    transport = StubMcpTransport(
        {
            "tools/call": [
                {
                    "structuredContent": {
                        "tool": "cancel_run",
                        "status": "completed",
                        "result": {"runId": "run-2"},
                        "audit": {"auditId": "audit-3", "riskLevel": "execution"},
                        "entityRefs": {"proposalId": "proposal-2", "runId": "run-2"},
                    }
                }
            ]
        }
    )
    adapter = McpPlatformAdapter(transport=transport)

    result = adapter.resolve_approval(
        "confirm-2",
        True,
        CallerContext(
            session_id="session-1",
            agent_task_id="task-1",
            turn_id="turn-1",
            step_id="step-1",
        ),
    )

    assert result.state == GovernedActionState.EXECUTED
    assert transport.calls[0][1]["name"] == "resolve_confirmation"
    assert transport.calls[0][1]["arguments"] == {"confirmationId": "confirm-2", "decision": "approve"}


def test_mcp_read_resource_maps_json_resource() -> None:
    adapter = McpPlatformAdapter(
        transport=StubMcpTransport(
            {
                "resources/read": [
                    {
                        "contents": [
                            {
                                "uri": "mobiflow://resource/rh_1",
                                "mimeType": "application/json",
                                "text": '{"ok": true}',
                            }
                        ]
                    }
                ]
            }
        )
    )

    assert adapter.read_resource("rh_1") == {"ok": True}


def test_create_platform_adapter_defaults_to_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_MCP_URL", "http://control-service/mcp")
    monkeypatch.delenv("PLATFORM_ADAPTER_KIND", raising=False)

    adapter = create_platform_adapter()

    assert isinstance(adapter, McpPlatformAdapter)


def test_create_platform_adapter_can_select_http(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLATFORM_ADAPTER_KIND", "http")
    monkeypatch.setenv("PLATFORM_TOOL_BASE_URL", "http://control-service")

    adapter = create_platform_adapter()

    assert isinstance(adapter, HttpPlatformAdapter)


def test_submit_execution_proposal_maps_completed_response() -> None:
    transport = StubTransport(
        {
            ("POST", "/tools/execute"): [
                {
                    "tool": "propose_governed_action",
                    "status": "completed",
                    "result": {"status": "accepted"},
                    "warnings": ["policy logged"],
                    "audit": {"auditId": "audit-1", "riskLevel": "execution"},
                    "entityRefs": {"proposalId": "proposal-1", "runId": "run-1"},
                }
            ]
        }
    )
    adapter = HttpPlatformAdapter(transport=transport)

    result = adapter.submit_execution_proposal(
        proposal=ExecutionProposal(
            proposal_id="proposal-1",
            action_tool_name="cancel_run",
            arguments={"runId": "run-1"},
            target_kind=EntityKind.RUN,
            target_id="run-1",
            rationale="Cancel blocked run.",
        ),
        caller_context=CallerContext(
            session_id="session-1",
            agent_task_id="task-1",
            turn_id="turn-1",
            step_id="step-1",
        ),
    )

    assert result.state == GovernedActionState.EXECUTED
    assert result.audit is not None and result.audit.audit_id == "audit-1"
    assert result.entity_refs is not None and result.entity_refs.run_id == "run-1"
    assert result.warnings == ["policy logged"]


def test_submit_execution_proposal_maps_approval_required_response() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("POST", "/tools/execute"): [
                    {
                        "tool": "propose_governed_action",
                        "status": "approval_required",
                        "audit": {"auditId": "audit-2", "riskLevel": "execution"},
                        "entityRefs": {"proposalId": "proposal-2", "runId": "run-2"},
                        "confirmation": {
                            "confirmationId": "confirm-2",
                            "summary": "Approve cancelling run-2",
                            "expiresAt": 1710000000000,
                        },
                    }
                ]
            }
        )
    )

    result = adapter.submit_execution_proposal(
        proposal=ExecutionProposal(
            proposal_id="proposal-2",
            action_tool_name="cancel_run",
            arguments={"runId": "run-2"},
            target_kind=EntityKind.RUN,
            target_id="run-2",
            rationale="Cancel blocked run.",
        ),
        caller_context=CallerContext(
            session_id="session-1",
            agent_task_id="task-1",
            turn_id="turn-1",
            step_id="step-1",
        ),
    )

    assert result.state == GovernedActionState.APPROVAL_REQUIRED
    assert result.confirmation_id == "confirm-2"
    assert result.confirmation_summary == "Approve cancelling run-2"
    assert result.confirmation_expires_at == 1710000000000
    assert result.audit is not None and result.audit.audit_id == "audit-2"
    assert result.entity_refs is not None and result.entity_refs.proposal_id == "proposal-2"


def test_observe_run_maps_snapshots_diagnosis_and_artifacts() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("POST", "/tools/execute"): [
                    {
                        "tool": "get_run_governance_snapshot",
                        "status": "completed",
                        "audit": {"auditId": "audit-governance", "riskLevel": "discovery"},
                        "result": {
                            "runId": "run-1",
                            "status": "BLOCKED",
                            "blockers": [{"code": "executor_stalled"}],
                            "latestAttemptIds": ["attempt-1"],
                            "lastUpdatedAt": 1710000000100,
                        },
                    },
                    {
                        "tool": "get_run_lineage_snapshot",
                        "status": "completed",
                        "audit": {"auditId": "audit-lineage", "riskLevel": "discovery"},
                        "result": {
                            "runId": "run-1",
                            "currentGovernedOptions": ["cancel_run"],
                            "latestArtifacts": [
                                {
                                    "artifactId": "artifact-1",
                                    "artifactType": "log",
                                    "fileName": "attempt.log",
                                    "createdAt": 1710000000200,
                                    "resource": {"handle": "res://artifact-1"},
                                }
                            ],
                        },
                    },
                    {
                        "tool": "get_attempt_diagnosis_bundle",
                        "status": "completed",
                        "audit": {"auditId": "audit-diagnosis", "riskLevel": "discovery"},
                        "result": {
                            "attemptId": "attempt-1",
                            "keyEvents": [{"eventType": "STALL", "message": "Executor stalled"}],
                            "failureSignals": [{"code": "stalled"}],
                        },
                    },
                ]
            }
        )
    )

    observation = adapter.observe_run("run-1")
    facts = {fact.fact_id: fact for fact in observation.facts}

    assert RUN_GOVERNANCE_FACT_ID in facts
    assert RUN_LINEAGE_FACT_ID in facts
    assert RUN_ARTIFACTS_FACT_ID in facts
    assert ATTEMPT_DIAGNOSIS_FACT_ID in facts
    assert observation.resource_handles == ["res://artifact-1"]
    assert any(inference.inference_id.endswith("cancel-available") for inference in observation.inferences)
    assert facts[RUN_GOVERNANCE_FACT_ID].evidence_refs[0].evidence_id == "snapshot:get_run_governance_snapshot:run:run-1"
    assert facts[RUN_ARTIFACTS_FACT_ID].evidence_refs[0].evidence_id == "artifact:artifact-1"


def test_observe_target_dispatches_to_run_and_attempt_observation() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("POST", "/tools/execute"): [
                    {
                        "tool": "get_run_governance_snapshot",
                        "status": "completed",
                        "result": {
                            "runId": "run-1",
                            "status": "BLOCKED",
                            "latestAttemptIds": ["attempt-1"],
                            "lastUpdatedAt": 1710000000100,
                        },
                    },
                    {
                        "tool": "get_run_lineage_snapshot",
                        "status": "completed",
                        "result": {"runId": "run-1", "latestArtifacts": []},
                    },
                    {
                        "tool": "get_attempt_diagnosis_bundle",
                        "status": "completed",
                        "result": {"attemptId": "attempt-1", "failureSignals": [{"code": "stalled"}]},
                    },
                    {
                        "tool": "get_attempt_diagnosis_bundle",
                        "status": "completed",
                        "result": {"attemptId": "attempt-2", "failureSignals": [{"code": "blocked"}]},
                    },
                ]
            }
        )
    )

    run_observation = adapter.observe_target(EntityKind.RUN, "run-1")
    attempt_observation = adapter.observe_target(EntityKind.ATTEMPT, "attempt-2")

    assert run_observation.focus_kind == EntityKind.RUN
    assert attempt_observation.focus_kind == EntityKind.ATTEMPT
    assert any(fact.fact_id == ATTEMPT_DIAGNOSIS_FACT_ID for fact in attempt_observation.facts)


def test_observe_target_rejects_unsupported_http_target() -> None:
    adapter = HttpPlatformAdapter(transport=StubTransport({}))

    with pytest.raises(PlatformAdapterError, match="cannot observe target kind device"):
        adapter.observe_target(EntityKind.DEVICE, "device-1")


def test_fake_adapter_observe_target_dispatches_and_rejects_unknown_kind() -> None:
    run_observation = ObservationView(
        observation_id="observation:run:1",
        focus_kind=EntityKind.RUN,
        focus_id="run-1",
    )
    attempt_observation = ObservationView(
        observation_id="observation:attempt:1",
        focus_kind=EntityKind.ATTEMPT,
        focus_id="attempt-1",
    )
    adapter = FakePlatformAdapter(
        run_observations={"run-1": run_observation},
        attempt_observations={"attempt-1": attempt_observation},
    )

    assert adapter.observe_target(EntityKind.RUN, "run-1").observation_id == "observation:run:1"
    assert adapter.observe_target(EntityKind.ATTEMPT, "attempt-1").observation_id == "observation:attempt:1"
    with pytest.raises(PlatformAdapterError, match="cannot observe target kind device"):
        adapter.observe_target(EntityKind.DEVICE, "device-1")


def test_query_audit_timeline_maps_entity_refs() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("POST", "/tools/audits/query"): [
                    {
                        "entries": [
                            {
                                "auditId": "audit-9",
                                "riskLevel": "execution",
                                "tool": "cancel_run",
                                "status": "completed",
                                "callerContext": {
                                    "agentTaskId": "task-1",
                                    "turnId": "turn-1",
                                    "stepId": "step-1",
                                },
                                "entityRefs": {
                                    "proposalId": "proposal-9",
                                    "runId": "run-9",
                                    "artifactIds": ["artifact-9"],
                                },
                                "createdAt": 1710000000000,
                                "updatedAt": 1710000001000,
                            }
                        ]
                    }
                ]
            }
        )
    )

    entries = adapter.query_audit_timeline(runId="run-9")

    assert len(entries) == 1
    assert entries[0].audit.audit_id == "audit-9"
    assert entries[0].entity_refs.proposal_id == "proposal-9"
    assert entries[0].entity_refs.artifact_ids == ["artifact-9"]


def test_get_run_target_and_attempt_map_context_objects() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("POST", "/tools/execute"): [
                    {
                        "tool": "get_run_target",
                        "status": "completed",
                        "result": {
                            "runTargetId": "rt-1",
                            "deviceId": "device-1",
                            "status": "FAILED",
                            "attemptCount": 2,
                            "currentTaskId": "task-1",
                            "latestAttemptId": "attempt-1",
                            "failureReason": "ui_not_found",
                            "latestAttempt": {
                                "attemptId": "attempt-1",
                                "taskId": "task-1",
                                "deviceId": "device-1",
                                "runId": "run-1",
                                "status": "FAILED",
                                "finalState": "FAILED",
                            },
                        },
                    },
                    {
                        "tool": "get_attempt",
                        "status": "completed",
                        "result": {
                            "attempt": {
                                "attemptId": "attempt-1",
                                "taskId": "task-1",
                                "deviceId": "device-1",
                                "runId": "run-1",
                                "status": "FAILED",
                                "finalState": "FAILED",
                            },
                            "events": [],
                            "artifacts": [],
                        },
                    },
                ]
            }
        )
    )

    run_target = adapter.get_run_target("rt-1")
    attempt = adapter.get_attempt("attempt-1")

    assert run_target.run_target_id == "rt-1"
    assert run_target.latest_attempt is not None
    assert run_target.latest_attempt.run_id == "run-1"
    assert attempt.attempt_id == "attempt-1"
    assert attempt.run_id == "run-1"


def test_get_run_governance_snapshot_and_lineage_snapshot_map_typed_objects() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("POST", "/tools/execute"): [
                    {
                        "tool": "get_run_governance_snapshot",
                        "status": "completed",
                        "result": {
                            "runId": "run-1",
                            "status": "FAILED",
                            "targetCounts": {
                                "totalTargets": 1,
                                "queued": 0,
                                "running": 0,
                                "retryPending": 0,
                                "succeeded": 0,
                                "failed": 1,
                                "cancelled": 0,
                            },
                            "attemptCounts": {
                                "total": 1,
                                "running": 0,
                                "failed": 1,
                                "succeeded": 0,
                            },
                            "latestAttemptIds": ["attempt-1"],
                            "blockers": ["terminal_failure"],
                            "lastUpdatedAt": 1710000001000,
                        },
                    },
                    {
                        "tool": "get_run_lineage_snapshot",
                        "status": "completed",
                        "result": {
                            "runId": "run-1",
                            "run": {
                                "run": {
                                    "runId": "run-1",
                                    "name": "Original Run",
                                    "poolId": "pool-1",
                                    "status": "FAILED",
                                    "taskType": "smoke",
                                    "profilePackage": "profiles.demo",
                                    "priority": 5,
                                    "labels": ["nightly"],
                                    "source": "agent",
                                    "createdBy": "tester",
                                    "maxRetriesPerDevice": 1,
                                    "queueTimeoutMs": 60000,
                                    "cancelRequested": False,
                                    "counts": {
                                        "totalTargets": 1,
                                        "queued": 0,
                                        "running": 0,
                                        "retryPending": 0,
                                        "succeeded": 0,
                                        "failed": 1,
                                        "cancelled": 0,
                                    },
                                },
                                "taskPayload": {"entry": "home"},
                                "runConfig": {"env": "staging"},
                                "artifactPolicy": {"retainDays": 7},
                                "targets": [
                                    {
                                        "runTargetId": "rt-1",
                                        "deviceId": "device-1",
                                        "status": "FAILED",
                                        "attemptCount": 1,
                                        "latestAttemptId": "attempt-1",
                                    }
                                ],
                            },
                            "targets": [
                                {
                                    "runTargetId": "rt-1",
                                    "deviceId": "device-1",
                                    "status": "FAILED",
                                    "attemptCount": 1,
                                    "latestAttemptId": "attempt-1",
                                }
                            ],
                            "attempts": [
                                {
                                    "attemptId": "attempt-1",
                                    "taskId": "task-1",
                                    "deviceId": "device-1",
                                    "runId": "run-1",
                                    "status": "FAILED",
                                    "finalState": "FAILED",
                                }
                            ],
                            "latestArtifacts": [
                                {
                                    "artifactId": "artifact-1",
                                    "attemptId": "attempt-1",
                                    "taskId": "task-1",
                                    "runId": "run-1",
                                    "artifactType": "screenshot",
                                    "fileName": "shot.png",
                                    "mimeType": "image/png",
                                    "sizeBytes": 128,
                                    "createdAt": 1710000002000,
                                    "resource": {"handle": "res://artifact-1"},
                                }
                            ],
                            "auditRefs": [
                                {
                                    "auditId": "audit-1",
                                    "requestId": "req-1",
                                    "sessionId": "session-1",
                                    "tool": "generate_failure_triage",
                                    "status": "completed",
                                    "riskLevel": "advisory",
                                    "entityRefs": {"runId": "run-1", "artifactIds": []},
                                    "createdAt": 1710000002001,
                                    "updatedAt": 1710000002002,
                                }
                            ],
                            "blockers": ["terminal_failure"],
                            "currentGovernedOptions": ["create_run", "continue_observe"],
                        },
                    },
                ]
            }
        )
    )

    governance = adapter.get_run_governance_snapshot("run-1")
    lineage = adapter.get_run_lineage_snapshot("run-1")

    assert governance.run_id == "run-1"
    assert governance.attempt_counts.failed == 1
    assert governance.blockers == ["terminal_failure"]
    assert lineage.run.run.pool_id == "pool-1"
    assert lineage.run.task_payload == {"entry": "home"}
    assert lineage.latest_artifacts[0].resource_handle == "res://artifact-1"
    assert lineage.current_governed_options == ["create_run", "continue_observe"]


def test_failure_triage_and_guidance_mapping() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("POST", "/tools/execute"): [
                    {
                        "tool": "generate_failure_triage",
                        "status": "completed",
                        "result": {
                            "triageResultId": "triage-1",
                            "runTargetId": "rt-1",
                            "result": {
                                "failureCategory": "UI_NOT_FOUND",
                                "probableCause": "Login button was not visible.",
                                "confidence": 0.87,
                                "retryRecommendation": "INSPECT_PROFILE",
                                "suggestedNextAction": "INSPECT_ARTIFACTS",
                                "operatorReviewHints": ["Check the latest screenshot."],
                                "evidence": ["artifact:shot-1"],
                            },
                            "validation": {
                                "valid": True,
                                "errors": [],
                                "warnings": ["Heuristic result."],
                            },
                            "modelMeta": {"provider": "test"},
                            "generatedAt": 1710000000000,
                        },
                    },
                    {
                        "tool": "get_latest_failure_triage",
                        "status": "completed",
                        "result": {
                            "triageResultId": "triage-2",
                            "runTargetId": "rt-1",
                            "result": {
                                "failureCategory": "NETWORK_ERROR",
                                "probableCause": "API timed out.",
                                "confidence": 0.73,
                                "retryRecommendation": "RETRY_OTHER_DEVICE",
                                "suggestedNextAction": "CHECK_CONTROL_PLANE",
                                "operatorReviewHints": [],
                                "evidence": ["event:attempt-1:0"],
                            },
                            "validation": {
                                "valid": True,
                                "errors": [],
                                "warnings": [],
                            },
                            "modelMeta": {"provider": "test"},
                            "generatedAt": 1710000001000,
                        },
                    },
                    {
                        "tool": "get_recovery_guidance_context",
                        "status": "completed",
                        "result": {
                            "entityKind": "run",
                            "entityId": "run-1",
                            "allowedActions": ["cancel_run", "continue_observe"],
                            "recommendedAction": "cancel_run",
                            "requiresApproval": True,
                            "requiredInputs": ["runId"],
                            "prerequisites": ["runId"],
                            "stopConditions": ["confirmation_pending"],
                            "stopConditionsSummary": "Stop when confirmation is pending.",
                            "whyNotOthers": "Other options do not clear the current blocker.",
                            "explanation": "The run is terminally blocked and should be cancelled.",
                            "confidence": 0.88,
                        },
                    },
                ]
            }
        )
    )

    generated = adapter.generate_failure_triage("rt-1")
    latest = adapter.get_latest_failure_triage("rt-1")
    guidance = adapter.get_recovery_guidance_context("run-1")

    assert generated.failure_category == FailureCategory.UI_NOT_FOUND
    assert generated.retry_recommendation == RetryRecommendation.INSPECT_PROFILE
    assert generated.suggested_next_action == SuggestedNextAction.INSPECT_ARTIFACTS
    assert generated.validation.warnings == ["Heuristic result."]
    assert latest.failure_category == FailureCategory.NETWORK_ERROR
    assert guidance.recommended_action == "cancel_run"
    assert guidance.requires_approval is True
    assert guidance.allowed_actions == ["cancel_run", "continue_observe"]


def test_generate_failure_triage_raises_platform_adapter_error_when_tool_fails() -> None:
    adapter = HttpPlatformAdapter(
        transport=StubTransport(
            {
                ("POST", "/tools/execute"): [
                    {
                        "tool": "generate_failure_triage",
                        "status": "failed",
                        "error": {
                            "code": "AI_FAILURE_TRIAGE_NOT_ALLOWED",
                            "message": "Failure triage is not allowed for this target.",
                            "retryable": False,
                        },
                    }
                ]
            }
        )
    )

    with pytest.raises(PlatformAdapterError, match="Failure triage is not allowed"):
        adapter.generate_failure_triage("rt-1")

