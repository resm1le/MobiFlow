from __future__ import annotations

import pytest

from mobiflow_agent.graph.routes import _normalize_route


class _State:
    def __init__(self, route_hint):
        self.route_hint = route_hint


def test_normalize_route_passes_known_step_hints() -> None:
    for hint in ("dynamic_observe", "decide_step", "dynamic_execute", "verify", "recover", "resume_approval", "finalize"):
        assert _normalize_route(hint) == hint


def test_normalize_route_passes_special_hints() -> None:
    assert _normalize_route("writeback_memory") == "writeback_memory"
    assert _normalize_route("verify_recovery") == "verify_recovery"


def test_normalize_route_raises_on_unknown_hint() -> None:
    with pytest.raises(ValueError, match="dynamic_exectue"):
        _normalize_route("dynamic_exectue")


def test_normalize_route_raises_on_none() -> None:
    with pytest.raises(ValueError):
        _normalize_route(None)
