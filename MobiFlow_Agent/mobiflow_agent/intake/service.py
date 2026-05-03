from __future__ import annotations

from typing import Any

from mobiflow_agent.graph import TaskGraphRuntime

from .interpreter import TaskInterpreter
from .models import TaskIntakeResult, TaskIntakeStatus
from .validation import TaskIntakeValidator
from .verification_factory import VerificationSpecFactory


class TaskIntakeService:
    def __init__(
        self,
        *,
        runtime: TaskGraphRuntime | None = None,
        interpreter: TaskInterpreter | None = None,
        validator: TaskIntakeValidator | None = None,
        verification_factory: VerificationSpecFactory | None = None,
    ) -> None:
        self._runtime = runtime or TaskGraphRuntime()
        self._interpreter = interpreter or TaskInterpreter()
        self._validator = validator or TaskIntakeValidator()
        self._verification_factory = verification_factory or VerificationSpecFactory()

    def create_session_from_text(
        self,
        raw_goal: str,
        *,
        platform_context: dict[str, Any] | None = None,
        confirmed: bool = False,
        session_id: str | None = None,
    ) -> TaskIntakeResult:
        interpreted = self._interpreter.interpret(raw_goal, platform_context=platform_context)
        if interpreted.spec is None:
            return interpreted
        validation = self._validator.validate(interpreted.spec, confirmed=confirmed)
        if not validation.accepted:
            return TaskIntakeResult(
                status=TaskIntakeStatus.NEEDS_CLARIFICATION,
                spec=interpreted.spec,
                clarification_questions=validation.clarification_questions or interpreted.clarification_questions,
                issues=validation.issues,
                trace_refs=interpreted.trace_refs,
            )
        verification_spec = self._verification_factory.build(interpreted.spec)
        session = self._runtime.create_session(
            interpreted.spec.normalized_goal,
            target_kind=interpreted.spec.target_kind,
            target_id=interpreted.spec.target_id,
            verification_spec=verification_spec,
            session_id=session_id,
        )
        return TaskIntakeResult(
            status=TaskIntakeStatus.READY,
            spec=interpreted.spec,
            session=session,
            trace_refs=interpreted.trace_refs,
        )


__all__ = ["TaskIntakeService"]
