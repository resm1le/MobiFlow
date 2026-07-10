"""Runtime state, checkpointing, and context compression for MobiFlow Agent."""

from importlib import import_module

from mobiflow_agent.runtime.checkpointing import (
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    create_checkpointer,
)
from mobiflow_agent.runtime.context import (
    ContextCompressionPolicy,
    ContextCompressionResult,
    ContextCompressionService,
    ContextHandoff,
    SessionContextDigest,
    StepContextSummary,
)
from mobiflow_agent.runtime.state import (
    AgentRuntimeState,
    CallerContext,
    ConfirmationState,
    PendingExecution,
    RecoveryExecutionContext,
    RecoveryObservationResult,
    RuntimeLifecycle,
)
__all__ = [
    "AgentRuntimeState",
    "CallerContext",
    "ConfirmationState",
    "ContextCompressionPolicy",
    "ContextCompressionResult",
    "ContextCompressionService",
    "ContextHandoff",
    "ExecutionTraceExporter",
    "PendingExecution",
    "RecoveryExecutionContext",
    "RecoveryObservationResult",
    "RuntimeCheckpointConfig",
    "RuntimeCheckpointMode",
    "RuntimeLifecycle",
    "SessionContextDigest",
    "StepContextSummary",
    "TestSuiteReportExporter",
    "create_checkpointer",
    "TaskHarnessError",
    "InMemoryTaskHarnessStore",
    "SqliteTaskHarnessStore",
    "TaskHarnessApprovalRequest",
    "TaskHarnessJob",
    "TaskHarnessJobPolicy",
    "TaskHarnessRequest",
    "TaskHarnessResponse",
    "TaskHarnessService",
    "TaskHarnessStatus",
    "TaskHarnessStore",
    "TaskHarnessStoreError",
    "TaskHarnessSerializationError",
    "TaskHeartbeatRunner",
    "TaskHarnessTransitionError",
]


def __getattr__(name: str):
    harness_exports = {
        "InMemoryTaskHarnessStore",
        "SqliteTaskHarnessStore",
        "TaskHarnessError",
        "TaskHarnessApprovalRequest",
        "TaskHarnessJob",
        "TaskHarnessJobPolicy",
        "TaskHarnessRequest",
        "TaskHarnessResponse",
        "TaskHarnessService",
        "TaskHarnessStatus",
        "TaskHarnessStore",
        "TaskHarnessStoreError",
        "TaskHarnessSerializationError",
        "TaskHeartbeatRunner",
        "TaskHarnessTransitionError",
    }
    if name in harness_exports:
        module = import_module("mobiflow_agent.runtime.harness")
        return getattr(module, name)
    if name == "ExecutionTraceExporter":
        module = import_module("mobiflow_agent.runtime.trace_export")
        return getattr(module, name)
    if name == "TestSuiteReportExporter":
        module = import_module("mobiflow_agent.runtime.suite_report_export")
        return getattr(module, name)
    raise AttributeError(f"module 'mobiflow_agent.runtime' has no attribute {name!r}")
