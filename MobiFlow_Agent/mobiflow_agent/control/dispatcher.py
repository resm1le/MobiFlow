from __future__ import annotations

from dataclasses import dataclass

from mobiflow_agent.agents.executor import ExecutorAgent
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.planner import PlannerAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.agents.verifier import VerifierAgent


@dataclass(slots=True)
class TaskAgentDispatcher:
    planner: PlannerAgent
    observer: ObserverAgent
    step_policy: StepPolicyAgent
    executor: ExecutorAgent | None
    verifier: VerifierAgent
    recovery: RecoveryAgent
