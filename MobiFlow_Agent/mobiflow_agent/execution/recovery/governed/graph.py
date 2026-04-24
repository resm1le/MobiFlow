from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from mobiflow_agent.execution.recovery.governed.nodes import (
    finalize,
    ingest_request,
    prepare_recovery,
    reobserve_recovery,
    resume_after_approval,
    submit_or_interrupt,
    verify_recovery,
)
from mobiflow_agent.execution.recovery.governed.routes import (
    route_after_prepare,
    route_after_resume,
    route_after_submit,
)
from mobiflow_agent.execution.recovery.proposal import GovernedRecoveryProposalService
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.runtime.checkpointing import (
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    create_checkpointer,
)
from mobiflow_agent.runtime.state import AgentRuntimeState


def build_governed_recovery_execution_graph(adapter: PlatformAdapter, *, checkpointer: Any | None = None):
    proposal_service = GovernedRecoveryProposalService(adapter)
    graph = StateGraph(AgentRuntimeState)
    graph.add_node("ingest_request", ingest_request)
    graph.add_node("prepare_recovery", lambda state: prepare_recovery(state, proposal_service))
    graph.add_node("submit_or_interrupt", lambda state: submit_or_interrupt(state, adapter))
    graph.add_node("resume_after_approval", lambda state: resume_after_approval(state, adapter))
    graph.add_node("reobserve_recovery", lambda state: reobserve_recovery(state, adapter))
    graph.add_node("verify_recovery", verify_recovery)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "ingest_request")
    graph.add_edge("ingest_request", "prepare_recovery")
    graph.add_conditional_edges(
        "prepare_recovery",
        route_after_prepare,
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
            "reobserve_recovery": "reobserve_recovery",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "resume_after_approval",
        route_after_resume,
        {
            "reobserve_recovery": "reobserve_recovery",
            "finalize": "finalize",
        },
    )
    graph.add_edge("reobserve_recovery", "verify_recovery")
    graph.add_edge("verify_recovery", "finalize")
    graph.add_edge("finalize", END)
    resolved_checkpointer = checkpointer or create_checkpointer(
        RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.MEMORY)
    )
    return graph.compile(
        checkpointer=resolved_checkpointer,
        interrupt_before=["resume_after_approval"],
        name="governed_recovery_execution_graph",
    )


__all__ = ["build_governed_recovery_execution_graph"]
