"""Platform integration boundary for MobiFlow Agent."""

from mobiflow_agent.platform.adapter import (
    FakePlatformAdapter,
    HttpPlatformAdapter,
    McpPlatformAdapter,
    PlatformAdapter,
    PlatformAdapterError,
    create_platform_adapter,
)
from mobiflow_agent.platform.simulation import (
    SimulatedActionTrace,
    SimulatedMobilePlatformAdapter,
    SimulatedMobileScenario,
    SimulatedScreen,
    SimulatedTransition,
    SimulatedUiNode,
)

__all__ = [
    "FakePlatformAdapter",
    "HttpPlatformAdapter",
    "McpPlatformAdapter",
    "PlatformAdapter",
    "PlatformAdapterError",
    "SimulatedActionTrace",
    "SimulatedMobilePlatformAdapter",
    "SimulatedMobileScenario",
    "SimulatedScreen",
    "SimulatedTransition",
    "SimulatedUiNode",
    "create_platform_adapter",
]
