"""Platform integration boundary for MobiFlow Agent."""

from mobiflow_agent.platform.adapter import (
    FakePlatformAdapter,
    HttpPlatformAdapter,
    PlatformAdapter,
    PlatformAdapterError,
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
    "PlatformAdapter",
    "PlatformAdapterError",
    "SimulatedActionTrace",
    "SimulatedMobilePlatformAdapter",
    "SimulatedMobileScenario",
    "SimulatedScreen",
    "SimulatedTransition",
    "SimulatedUiNode",
]
