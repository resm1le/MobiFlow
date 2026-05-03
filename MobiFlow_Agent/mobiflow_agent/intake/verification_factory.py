from __future__ import annotations

from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)

from .models import TaskIntakeSpec


class VerificationSpecFactory:
    def build(self, spec: TaskIntakeSpec) -> VerificationSpec:
        if spec.target_kind is None or spec.target_id is None:
            raise ValueError("VerificationSpecFactory requires target_kind and target_id.")
        if spec.verification_template == "home_screen_visible":
            return self._text_visible_spec(
                spec,
                check_id="home-screen-visible",
                description="Home Screen is visible.",
                default_text="Home Screen",
            )
        if spec.verification_template == "account_deleted_visible":
            return self._text_visible_spec(
                spec,
                check_id="account-deleted-visible",
                description="Account Deleted Screen is visible.",
                default_text="Account Deleted Screen",
            )
        raise ValueError(f"Unknown verification template: {spec.verification_template}")

    @staticmethod
    def _text_visible_spec(
        spec: TaskIntakeSpec,
        *,
        check_id: str,
        description: str,
        default_text: str,
    ) -> VerificationSpec:
        expected_text = str(spec.verification_params.get("expected_text") or default_text)
        return VerificationSpec(
            verification_id=f"verification:{spec.target_kind.value}:{spec.target_id}:{check_id}",
            target_kind=spec.target_kind or EntityKind.TASK,
            target_id=spec.target_id or spec.scenario_id or "task",
            success_checks=[
                VerificationCheck(
                    check_id=check_id,
                    description=description,
                    evidence_hint=expected_text,
                )
            ],
        )


__all__ = ["VerificationSpecFactory"]
