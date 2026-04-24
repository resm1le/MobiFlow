from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from mobiflow_agent.execution.recovery.blocked_run.nodes import (
    finalize,
    ingest_request,
    observe_run,
    plan_cancel_run,
    reobserve_run,
    resume_after_approval,
    submit_or_interrupt,
    verify_cancel_run,
)
from mobiflow_agent.execution.recovery.blocked_run.routes import (
    route_after_plan,
    route_after_resume,
    route_after_submit,
)
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.runtime.checkpointing import (
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    create_checkpointer,
)
from mobiflow_agent.runtime.state import AgentRuntimeState


def build_cancel_blocked_run_graph(adapter: PlatformAdapter, *, checkpointer: Any | None = None):
    graph = StateGraph(AgentRuntimeState)
    graph.add_node("ingest_request", ingest_request)
    graph.add_node("observe_run", lambda state: observe_run(state, adapter))
    graph.add_node("plan_cancel_run", plan_cancel_run)
    graph.add_node("submit_or_interrupt", lambda state: submit_or_interrupt(state, adapter))
    graph.add_node("resume_after_approval", lambda state: resume_after_approval(state, adapter))
    graph.add_node("reobserve_run", lambda state: reobserve_run(state, adapter))
    graph.add_node("verify_cancel_run", verify_cancel_run)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "ingest_request")
    graph.add_edge("ingest_request", "observe_run")
    graph.add_edge("observe_run", "plan_cancel_run")
    graph.add_conditional_edges(
        "plan_cancel_run",
        route_after_plan,
        {
            "submit_or_interrupt": "submit_or_interrupt",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "submit_or_interrupt",
        route_after_submit,
        {
            "resume_after_approval": "resume_after_approval",
            "reobserve_run": "reobserve_run",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "resume_after_approval",
        route_after_resume,
        {
            "reobserve_run": "reobserve_run",
            "finalize": "finalize",
        },
    )
    graph.add_edge("reobserve_run", "verify_cancel_run")
    graph.add_edge("verify_cancel_run", "finalize")
    graph.add_edge("finalize", END)
    resolved_checkpointer = checkpointer or create_checkpointer(
        RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.MEMORY)
    )
    return graph.compile(
        checkpointer=resolved_checkpointer,
        interrupt_before=["resume_after_approval"],
        name="cancel_blocked_run_graph",
    )


__all__ = ["build_cancel_blocked_run_graph"]
