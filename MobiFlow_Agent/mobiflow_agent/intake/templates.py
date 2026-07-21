from __future__ import annotations

from typing import Iterable

from pydantic import Field

from mobiflow_agent.common.contracts import ApprovalMode, DEFAULT_MOBILE_ACTIONS, EntityKind, StrictModel


class ScenarioTemplate(StrictModel):
    scenario_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    normalized_goal: str = Field(min_length=1)
    target_kind: EntityKind = EntityKind.TASK
    target_id: str = Field(min_length=1)
    verification_template: str = Field(min_length=1)
    verification_params: dict[str, str] = Field(default_factory=dict)
    allowed_actions: list[str] = Field(default_factory=lambda: list(DEFAULT_MOBILE_ACTIONS))
    approval_mode: ApprovalMode = ApprovalMode.ON_RISK
    needs_confirmation: bool = False
    risk_flags: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ScenarioTemplateRegistry:
    def __init__(self, templates: Iterable[ScenarioTemplate] = ()) -> None:
        self._templates = {template.scenario_id: template for template in templates}

    @classmethod
    def default(cls) -> "ScenarioTemplateRegistry":
        return cls(
            [
                ScenarioTemplate(
                    scenario_id="dynamic_login_success",
                    intent="mobile_login_experiment",
                    normalized_goal="Login to the demo app using bounded mobile UI actions.",
                    target_id="dynamic_login_success",
                    verification_template="home_screen_visible",
                    verification_params={"expected_text": "Home Screen"},
                    keywords=["login", "登录", "登陆", "demo app", "首页", "home"],
                ),
                ScenarioTemplate(
                    scenario_id="dynamic_fixed_script_contrast",
                    intent="permission_popup_contrast",
                    normalized_goal="Login while handling an unexpected permission dialog.",
                    target_id="dynamic_fixed_script_contrast",
                    verification_template="home_screen_visible",
                    verification_params={"expected_text": "Home Screen"},
                    keywords=["permission", "权限", "弹窗", "popup", "对比", "固定脚本"],
                ),
                ScenarioTemplate(
                    scenario_id="dynamic_slow_loading_recovery_success",
                    intent="slow_loading_recovery",
                    normalized_goal="Recover from slow loading and verify the home screen.",
                    target_id="dynamic_slow_loading_recovery_success",
                    verification_template="home_screen_visible",
                    verification_params={"expected_text": "Home Screen"},
                    keywords=["slow loading", "慢加载", "加载", "恢复", "retry"],
                ),
                ScenarioTemplate(
                    scenario_id="dynamic_approval_required_destructive_action",
                    intent="destructive_account_action",
                    normalized_goal="Delete the simulated account after explicit approval.",
                    target_id="dynamic_approval_required_destructive_action",
                    verification_template="account_deleted_visible",
                    verification_params={"expected_text": "Account Deleted Screen"},
                    allowed_actions=["mobile.tap"],
                    needs_confirmation=True,
                    risk_flags=["destructive_action"],
                    keywords=["delete account", "删除账号", "删除账户", "destructive"],
                ),
            ]
        )

    def get(self, scenario_id: str | None) -> ScenarioTemplate | None:
        if scenario_id is None:
            return None
        return self._templates.get(scenario_id)

    def visible_templates(self) -> list[dict]:
        return [template.model_dump(mode="python") for template in self._templates.values()]

    def match(self, raw_goal: str) -> ScenarioTemplate | None:
        normalized = raw_goal.casefold()
        scored = []
        for template in self._templates.values():
            score = sum(1 for keyword in template.keywords if keyword.casefold() in normalized)
            if score:
                scored.append((score, template))
        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1].scenario_id))
        return scored[0][1]

    def has_verification_template(self, name: str | None) -> bool:
        if name is None:
            return False
        return name in {"home_screen_visible", "account_deleted_visible"}

    @property
    def allowed_actions(self) -> set[str]:
        actions: set[str] = set()
        for template in self._templates.values():
            actions.update(template.allowed_actions)
        return actions


__all__ = ["DEFAULT_MOBILE_ACTIONS", "ScenarioTemplate", "ScenarioTemplateRegistry"]
