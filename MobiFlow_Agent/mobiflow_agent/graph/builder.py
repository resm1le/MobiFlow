from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from mobiflow_agent.runtime.checkpointing import (
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    create_checkpointer,
)

from .nodes import (
    TaskGraphOps,
    activate_step,
    decide_step,
    dynamic_execute,
    dynamic_observe,
    ensure_plan,
    finalize,
    recover,
    resume_approval,
    verify,
    verify_recovery,
    writeback_memory,
)
from .routes import (
    route_after_ensure_plan,
    route_after_decide_step,
    route_after_dynamic_execute,
    route_after_recovery_verify,
    route_after_resume,
    route_after_recover,
    route_after_step,
    route_after_verify,
    route_after_writeback,
)
from .state import TaskGraphState


def build_task_orchestration_graph(
    ops: TaskGraphOps,
    *,
    checkpointer: Any | None = None,
):
    graph = StateGraph(TaskGraphState)
    graph.add_node("ensure_plan", lambda state: ensure_plan(state, ops))
    graph.add_node("activate_step", lambda state: activate_step(state, ops))
    graph.add_node("dynamic_observe", lambda state: dynamic_observe(state, ops))
    graph.add_node("decide_step", lambda state: decide_step(state, ops))
    graph.add_node("dynamic_execute", lambda state: dynamic_execute(state, ops))
    graph.add_node("resume_approval", lambda state: resume_approval(state, ops))
    graph.add_node("verify", lambda state: verify(state, ops))
    graph.add_node("recover", lambda state: recover(state, ops))
    graph.add_node("verify_recovery", lambda state: verify_recovery(state, ops))
    graph.add_node("writeback_memory", lambda state: writeback_memory(state, ops))
    graph.add_node("finalize", lambda state: finalize(state, ops))

    graph.add_edge(START, "ensure_plan")
    graph.add_conditional_edges(
        "ensure_plan",
        route_after_ensure_plan,
        _step_routes(include_resume=True),
    )
    graph.add_conditional_edges("activate_step", route_after_step, _step_routes())
    graph.add_conditional_edges(
        "dynamic_observe",
        route_after_step,
        _step_routes(),
    )
    graph.add_conditional_edges(
        "decide_step",
        route_after_decide_step,
        _step_routes(),
    )
    graph.add_conditional_edges(
        "dynamic_execute",
        route_after_dynamic_execute,
        _step_routes(),
    )
    graph.add_conditional_edges(
        "resume_approval",
        route_after_resume,
        {
            "dynamic_observe": "dynamic_observe",
            "verify": "verify",
            "recover": "recover",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "verify",
        route_after_verify,
        {
            "writeback_memory": "writeback_memory",
            "recover": "recover",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "recover",
        route_after_recover,
        {
            "dynamic_observe": "dynamic_observe",
            "verify": "verify",
            "recover": "recover",
            "verify_recovery": "verify_recovery",
            "writeback_memory": "writeback_memory",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "verify_recovery",
        route_after_recovery_verify,
        {
            "writeback_memory": "writeback_memory",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "writeback_memory",
        route_after_writeback,
        _step_routes(),
    )
    graph.add_edge("finalize", END)

    resolved_checkpointer = checkpointer or create_checkpointer(
        RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.MEMORY)
    )
    return graph.compile(
        checkpointer=resolved_checkpointer,
        name="task_orchestration_graph",
    )


def _step_routes(*, include_resume: bool = False) -> dict[str, str]:
    routes = {
        "verify": "verify",
        "recover": "recover",
        "finalize": "finalize",
        "dynamic_observe": "dynamic_observe",
        "decide_step": "decide_step",
        "dynamic_execute": "dynamic_execute",
    }
    if include_resume:
        routes["resume_approval"] = "resume_approval"
    return routes


__all__ = ["build_task_orchestration_graph"]
