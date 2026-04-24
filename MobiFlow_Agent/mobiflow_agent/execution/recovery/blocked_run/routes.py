from __future__ import annotations

from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle


def route_after_submit(state: AgentRuntimeState) -> str:
    if state.latest_verdict is not None:
        return "finalize"
    pending = state.pending_execution
    if pending and state.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL:
        return "resume_after_approval"
    if state.lifecycle == RuntimeLifecycle.EXECUTING:
        return "reobserve_run"
    return "finalize"


def route_after_plan(state: AgentRuntimeState) -> str:
    if state.latest_verdict is not None or state.pending_execution is None:
        return "finalize"
    return "submit_or_interrupt"


def route_after_resume(state: AgentRuntimeState) -> str:
    if state.latest_verdict is not None:
        return "finalize"
    if state.lifecycle == RuntimeLifecycle.EXECUTING:
        return "reobserve_run"
    return "finalize"


__all__ = ["route_after_plan", "route_after_resume", "route_after_submit"]
