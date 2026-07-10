from __future__ import annotations

from mobiflow_agent.common.contracts import (
    EntityKind,
    StrictModel,
    VerificationCheck,
    VerificationSpec,
)

from .models import TestCase


class SessionAssembly(StrictModel):
    goal: str
    target_kind: EntityKind
    target_id: str
    verification_spec: VerificationSpec


class TestCaseAssembler:
    def assemble(
        self, test_case: TestCase, success_checks: list[VerificationCheck]
    ) -> SessionAssembly:
        if not success_checks:
            raise ValueError("TestCaseAssembler requires at least one success check.")
        target_kind = EntityKind.TASK
        target_id = test_case.case_id
        spec = VerificationSpec(
            verification_id=f"verification:{target_kind.value}:{target_id}:testcase",
            target_kind=target_kind,
            target_id=target_id,
            success_checks=list(success_checks),
        )
        return SessionAssembly(
            goal=test_case.normalized_goal,
            target_kind=target_kind,
            target_id=target_id,
            verification_spec=spec,
        )


__all__ = ["SessionAssembly", "TestCaseAssembler"]
