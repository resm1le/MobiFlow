from __future__ import annotations

from typing import Any

from mobiflow_agent.graph import TaskGraphRuntime

from .assembler import TestCaseAssembler
from .interpreter import TaskInterpreter, TestCaseParser
from .models import TaskIntakeResult, TaskIntakeStatus
from .synthesizer import AssertionSynthesizer
from .validation import TaskIntakeValidator, TestCaseValidator
from .verification_factory import VerificationSpecFactory


class TaskIntakeService:
    def __init__(
        self,
        *,
        runtime: TaskGraphRuntime | None = None,
        interpreter: TaskInterpreter | None = None,
        validator: TaskIntakeValidator | None = None,
        verification_factory: VerificationSpecFactory | None = None,
        parser: TestCaseParser | None = None,
        testcase_validator: TestCaseValidator | None = None,
        synthesizer: AssertionSynthesizer | None = None,
        assembler: TestCaseAssembler | None = None,
    ) -> None:
        self._runtime = runtime or TaskGraphRuntime()
        self._interpreter = interpreter or TaskInterpreter()
        self._validator = validator or TaskIntakeValidator()
        self._verification_factory = verification_factory or VerificationSpecFactory()
        self._parser = parser or TestCaseParser()
        self._testcase_validator = testcase_validator or TestCaseValidator()
        self._synthesizer = synthesizer or AssertionSynthesizer()
        self._assembler = assembler or TestCaseAssembler()

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

    def submit_test_case(
        self,
        test_case_text: str,
        *,
        platform_context: dict[str, Any] | None = None,
        confirmed: bool = False,
        session_id: str | None = None,
    ) -> TaskIntakeResult:
        parsed = self._parser.parse(test_case_text, platform_context=platform_context)
        if parsed.test_case is None:
            return parsed
        test_case = parsed.test_case
        trace_refs = list(parsed.trace_refs)

        validation = self._testcase_validator.validate(test_case, confirmed=confirmed)
        if not validation.accepted:
            return TaskIntakeResult(
                status=TaskIntakeStatus.NEEDS_CLARIFICATION,
                test_case=test_case,
                clarification_questions=validation.clarification_questions,
                issues=validation.issues,
                trace_refs=trace_refs,
            )

        synthesis = self._synthesizer.synthesize(test_case)
        trace_refs.extend(synthesis.trace_refs)
        if not synthesis.accepted:
            return TaskIntakeResult(
                status=TaskIntakeStatus.NEEDS_CLARIFICATION,
                test_case=test_case,
                clarification_questions=synthesis.clarification_questions,
                issues=synthesis.issues,
                trace_refs=trace_refs,
            )

        assembly = self._assembler.assemble(test_case, synthesis.checks)
        session = self._runtime.create_session(
            assembly.goal,
            target_kind=assembly.target_kind,
            target_id=assembly.target_id,
            verification_spec=assembly.verification_spec,
            session_id=session_id,
        )
        return TaskIntakeResult(
            status=TaskIntakeStatus.READY,
            test_case=test_case,
            session=session,
            trace_refs=trace_refs,
        )


__all__ = ["TaskIntakeService"]
