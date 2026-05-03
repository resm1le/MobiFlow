from __future__ import annotations

from .state import TaskGraphState


_STEP_ROUTES = {
    "dynamic_observe",
    "decide_step",
    "dynamic_execute",
    "verify",
    "recover",
    "resume_approval",
    "finalize",
}


def route_after_ensure_plan(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def route_after_step(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def route_after_decide_step(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def route_after_dynamic_execute(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def route_after_resume(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def route_after_verify(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def route_after_recover(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def route_after_recovery_verify(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def route_after_writeback(state: TaskGraphState) -> str:
    return _normalize_route(state.route_hint)


def _normalize_route(route_hint: str | None) -> str:
    if route_hint in _STEP_ROUTES:
        return route_hint
    if route_hint == "writeback_memory":
        return "writeback_memory"
    if route_hint == "verify_recovery":
        return "verify_recovery"
    return "finalize"


__all__ = [
    "route_after_ensure_plan",
    "route_after_decide_step",
    "route_after_dynamic_execute",
    "route_after_recover",
    "route_after_recovery_verify",
    "route_after_resume",
    "route_after_step",
    "route_after_verify",
    "route_after_writeback",
]
