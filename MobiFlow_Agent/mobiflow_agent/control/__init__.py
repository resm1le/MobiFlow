"""Task-control-plane orchestration entry points."""

from importlib import import_module

from mobiflow_agent.control.dispatcher import TaskAgentDispatcher
from mobiflow_agent.control.policy import TaskControlPolicy

__all__ = [
    "TaskAgentDispatcher",
    "TaskControlPolicy",
    "TaskOrchestratorService",
]


def __getattr__(name: str):
    if name == "TaskOrchestratorService":
        module = import_module("mobiflow_agent.control.orchestrator")
        return module.TaskOrchestratorService
    raise AttributeError(f"module 'mobiflow_agent.control' has no attribute {name!r}")
