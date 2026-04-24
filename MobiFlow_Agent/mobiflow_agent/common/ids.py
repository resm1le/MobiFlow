"""Stable id builders for task-control-plane objects."""

from __future__ import annotations

from uuid import uuid4


def _build_id(prefix: str) -> str:
    return f"{prefix}:{uuid4().hex}"


def build_task_session_id() -> str:
    return _build_id("task-session")


def build_task_contract_id() -> str:
    return _build_id("task-contract")


def build_task_plan_id() -> str:
    return _build_id("task-plan")


def build_task_step_id() -> str:
    return _build_id("task-step")


def build_role_request_id() -> str:
    return _build_id("role-request")


def build_role_result_id() -> str:
    return _build_id("role-result")
