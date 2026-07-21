from __future__ import annotations

from typing import Protocol, runtime_checkable

from mobiflow_agent.common.contracts import ExecutionProposal
from mobiflow_agent.platform.types import (
    DispatchDeviceContext,
    GovernedActionResult,
    RunPlanningCatalogContext,
)
from mobiflow_agent.runtime.state import CallerContext


@runtime_checkable
class CollectionDispatchPlatform(Protocol):
    def list_devices(self) -> list[DispatchDeviceContext]: ...

    def get_run_planning_catalog(self) -> RunPlanningCatalogContext: ...

    def submit_execution_proposal(
        self,
        proposal: ExecutionProposal,
        caller_context: CallerContext,
    ) -> GovernedActionResult: ...


__all__ = ["CollectionDispatchPlatform"]
