# TestCase Intake Pipeline (L0 + L1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn task-intake from a hardcoded-4-scenario template gate into a natural-language TestCase compiler — the L0+L1 foundation of MobiFlow's pivot to a natural-language-driven real-device regression-testing platform.

**Architecture:** A four-stage intake pipeline (`TestCaseParser → TestCaseValidator → AssertionSynthesizer → TestCaseAssembler`) produces a first-class `TestCase` (goal + expected outcomes), then translates it into the `(TaskSession, VerificationSpec)` the crown layer (Verifier/Recovery/Memory) consumes. Templates demote from admission gate to few-shot seeds. One bounded crown edit adds a `NOT_EXISTS` predicate operator so disappearance assertions are representable.

**Tech Stack:** Python 3.11, pydantic v2 (`StrictModel`, `extra="forbid"`), LangGraph, existing `ModelRuntime.generate_structured`. Tests: pytest (`pip install -e '.[dev]'`), run from `MobiFlow_Agent/`.

## Global Constraints

Every task's requirements implicitly include this section. Values copied verbatim from the design spec (`docs/superpowers/specs/2026-07-09-testcase-intake-l0-l1-design.md`).

- **G1 — Minimal crown change, one operator only.** The ONLY permitted crown-layer edit is adding `NOT_EXISTS` to `VerificationPredicateOperator` and its evaluation branch in `verifier._predicate_values_match`. `RecoveryAgent`, `Memory`, and the rest of `VerifierAgent` are untouched. Any other crown change is out of scope and must be escalated.
- **G2 — Assertions confined to the (now 6-member) predicate vocabulary.** Synthesized `VerificationCheck.predicates` use only `VerificationPredicateOperator` members. Out-of-vocabulary → reject/retry, never smuggle.
- **G3 — Crown contracts stay `extra="forbid"`.** `VerificationCheck`/`VerificationPredicate`/`VerificationSpec` are `StrictModel`. Do NOT add `origin`/`confidence` to them. All intake-only metadata lives on `TestCase`.
- **G4 — L2/L3 seams preserved.** `TestCase` is the stable input atom; `submit_test_case` takes one case now, a suite later.
- **G5 — Simulation-first.** Phase 1 correctness is defined and tested against the simulation adapter's fact vocabulary (`mobile_observation_summary`, `simulated_screen_snapshot`, `simulated_ui_tree`). Real-device fact resolution is a named follow-up, not a Phase-1 acceptance criterion. Do NOT write real-device fact assertions.
- **G6 — Evidence-first.** Every signature/shape below was verified against real code.
- **Low-confidence lever:** confidence-threshold emission + `TestCase.needs_confirmation`. `required=False` is NOT the lever — it softens step-advance but NOT the final verdict (verifier.py:242-254 counts every unmatched success_check into `unmatched_check_ids`).

---

## File Structure

**Crown (bounded G1 edit):**
- Modify `MobiFlow_Agent/mobiflow_agent/common/contracts.py` — add `NOT_EXISTS = "not_exists"` to `VerificationPredicateOperator` (currently lines 174-179).
- Modify `MobiFlow_Agent/mobiflow_agent/agents/verifier.py` — add symmetric branch in `_predicate_values_match` (currently lines 453-466).

**Intake (`MobiFlow_Agent/mobiflow_agent/intake/`):**
- Modify `models.py` — add `AssertionPredicate`, `ExpectedOutcome`, `TestStep`, `OutcomeOrigin`, `TestCase`; add optional `test_case` field to `TaskIntakeResult`.
- Rewrite `interpreter.py` — add `TestCaseParser` (keep `TaskInterpreter` untouched for back-compat).
- Rewrite `validation.py` — add `TestCaseValidator` (keep `TaskIntakeValidator` untouched for back-compat).
- Create `synthesizer.py` — `AssertionSynthesizer` + `SynthesizedAssertion` response model + synthesis validator.
- Create `assembler.py` — `TestCaseAssembler`.
- Modify `prompting.py` — add `AssertionSynthesizerPromptBuilder` and `TestCaseParserPromptBuilder`.
- Modify `service.py` — add `submit_test_case`; make `create_session_from_text` a thin forwarder.
- Modify `__init__.py` — export new symbols.
- Modify `MobiFlow_Agent/README.md` — update Natural Language Intake section.

**Tests (`MobiFlow_Agent/tests/`):**
- Modify `tests/agents/test_verifier_agent.py` — `NOT_EXISTS` tests incl. absence caveat.
- Create `tests/intake/test_testcase_models.py`
- Create `tests/intake/test_testcase_parser.py`
- Create `tests/intake/test_testcase_validator.py`
- Create `tests/intake/test_assertion_synthesizer.py`
- Create `tests/intake/test_testcase_assembler.py`
- Create `tests/intake/test_submit_test_case.py` (service back-compat + full prose→verdict against SIMULATION adapter).

**Design decisions locked here:**
- New classes are ADDITIVE. Existing `TaskInterpreter`, `TaskIntakeValidator`, `VerificationSpecFactory`, `TaskIntakeSpec` stay so the current `create_session_from_text` template path and its tests keep passing during the transition; `submit_test_case` is the new NL path. This avoids a big-bang rewrite while `test_task_intake.py` still asserts the template behavior.
- `SynthesizedAssertion` is intake-internal (may carry `confidence`); it is translated into strict `VerificationCheck`/`VerificationPredicate` at the assembler boundary (G3).

---

## Task 1: Crown addition — `NOT_EXISTS` operator

**Files:**
- Modify: `MobiFlow_Agent/mobiflow_agent/common/contracts.py:174-179`
- Modify: `MobiFlow_Agent/mobiflow_agent/agents/verifier.py:453-456`
- Test: `MobiFlow_Agent/tests/agents/test_verifier_agent.py`

**Interfaces:**
- Produces: `VerificationPredicateOperator.NOT_EXISTS` (value `"not_exists"`); `_predicate_values_match` returns `not bool(values)` for it. Consumed by Tasks 5-8.

**Semantics caveat (from spec §crown-addition point 3, corrected against real code):** `_matches_predicate` (verifier.py:419-430) iterates `candidate_facts = [f for f in observation.facts if predicate.fact_id is None or f.fact_id == predicate.fact_id]`; if that list is empty it returns `False` before ever calling `_predicate_values_match`. So a `NOT_EXISTS` predicate whose specific `fact_id` was NOT observed evaluates to `False` (does not match). `NOT_EXISTS` matches only when the fact IS present but the `field_path` resolves to nothing. Therefore synthesis (Task 5) MUST anchor `NOT_EXISTS` to a reliably-present `fact_id` (e.g. `simulated_screen_snapshot`). The tests below pin exactly this behavior.

- [ ] **Step 1: Write the failing operator-value test**

Add to `MobiFlow_Agent/tests/agents/test_verifier_agent.py`:

```python
def test_verifier_agent_not_exists_matches_when_node_absent_on_present_screen() -> None:
    spec = VerificationSpec(
        verification_id="verification:logout",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        success_checks=[
            VerificationCheck(
                check_id="login-button-gone",
                description="Login button is no longer present.",
                predicates=[
                    VerificationPredicate(
                        fact_id="simulated_ui_tree",
                        field_path="value[].node_id",
                        operator=VerificationPredicateOperator.NOT_EXISTS,
                    )
                ],
            )
        ],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-home",
        focus_kind=EntityKind.TASK,
        focus_id="task-1",
        facts=[
            ObservationFact(
                fact_id="simulated_ui_tree",
                source=ObservationFactSource.PLATFORM,
                title="Tree",
                value=[],
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="tree-evidence",
                        kind=EvidenceKind.ARTIFACT,
                        summary="Empty tree.",
                        locator="home",
                    )
                ],
            )
        ],
    )

    verdict, _ = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert verdict.matched_check_ids == ["login-button-gone"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/agents/test_verifier_agent.py::test_verifier_agent_not_exists_matches_when_node_absent_on_present_screen -v`
Expected: FAIL — `AttributeError: NOT_EXISTS` (enum member does not exist yet).

- [ ] **Step 3: Add the enum member**

In `MobiFlow_Agent/mobiflow_agent/common/contracts.py`, extend `VerificationPredicateOperator`:

```python
class VerificationPredicateOperator(str, Enum):
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    EQUALS = "equals"
    CONTAINS = "contains"
    ANY_EQUALS = "any_equals"
    ANY_CONTAINS = "any_contains"
```

- [ ] **Step 4: Add the evaluation branch**

In `MobiFlow_Agent/mobiflow_agent/agents/verifier.py`, inside `_predicate_values_match`, add the symmetric branch immediately after the `EXISTS` branch (currently line 455-456):

```python
    @staticmethod
    def _predicate_values_match(predicate: VerificationPredicate, values: list) -> bool:
        if predicate.operator == VerificationPredicateOperator.EXISTS:
            return bool(values)
        if predicate.operator == VerificationPredicateOperator.NOT_EXISTS:
            return not bool(values)
        if predicate.operator in {
            VerificationPredicateOperator.ANY_EQUALS,
            VerificationPredicateOperator.ANY_CONTAINS,
        }:
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/agents/test_verifier_agent.py::test_verifier_agent_not_exists_matches_when_node_absent_on_present_screen -v`
Expected: PASS.

- [ ] **Step 6: Write the absence-of-fact caveat test**

Add to `MobiFlow_Agent/tests/agents/test_verifier_agent.py` — pins that an unobserved specific `fact_id` does NOT match (short-circuit at verifier.py:419-430):

```python
def test_verifier_agent_not_exists_does_not_match_when_anchor_fact_unobserved() -> None:
    spec = VerificationSpec(
        verification_id="verification:logout",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        success_checks=[
            VerificationCheck(
                check_id="login-button-gone",
                description="Login button is no longer present.",
                predicates=[
                    VerificationPredicate(
                        fact_id="simulated_ui_tree",
                        field_path="value[].node_id",
                        operator=VerificationPredicateOperator.NOT_EXISTS,
                    )
                ],
            )
        ],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-other",
        focus_kind=EntityKind.TASK,
        focus_id="task-1",
        facts=[
            ObservationFact(
                fact_id="simulated_screen_snapshot",
                source=ObservationFactSource.PLATFORM,
                title="Screen",
                value={"screen_id": "home", "title": "Home Screen"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="screen-evidence",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Screen evidence.",
                        locator="home",
                    )
                ],
            )
        ],
    )

    verdict, _ = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.VERIFIED_UNKNOWN
    assert verdict.unmatched_check_ids == ["login-button-gone"]
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/agents/test_verifier_agent.py::test_verifier_agent_not_exists_does_not_match_when_anchor_fact_unobserved -v`
Expected: PASS (no impl change needed — this documents the anchor requirement that Task 5's prompt enforces).

- [ ] **Step 8: Run the full verifier + contracts suite for regressions**

Run: `pytest tests/agents/test_verifier_agent.py tests/common/test_contracts.py -v`
Expected: PASS (all existing tests still green; enum addition is backward compatible).

- [ ] **Step 9: Commit**

```bash
git add mobiflow_agent/common/contracts.py mobiflow_agent/agents/verifier.py tests/agents/test_verifier_agent.py
git commit -m "feat(verifier): add NOT_EXISTS predicate operator for disappearance assertions"
```

---

## Task 2: `TestCase` domain model

**Files:**
- Modify: `MobiFlow_Agent/mobiflow_agent/intake/models.py`
- Test: `MobiFlow_Agent/tests/intake/test_testcase_models.py`

**Interfaces:**
- Produces (all subclass `StrictModel`, consumed by Tasks 3-8):
  - `AssertionPredicate(str, Enum)`: `EXISTS, NOT_EXISTS, EQUALS, CONTAINS, ANY_EQUALS, ANY_CONTAINS` (exact string aliases of `VerificationPredicateOperator`).
  - `OutcomeOrigin(str, Enum)`: `MODEL_SYNTHESIZED, USER_AUTHORED, TEMPLATE`.
  - `ExpectedOutcome`: `raw_text: str`, `predicate: AssertionPredicate`, `observation_fact_id: str | None = None`, `field_path: str`, `expected_value: Any | None = None`, `confidence: float = 0.0` (0..1), `origin: OutcomeOrigin = MODEL_SYNTHESIZED`.
  - `TestStep`: `raw_text: str`, `hint_action: str | None = None`.
  - `TestCase`: `case_id: str`, `raw_goal: str`, `normalized_goal: str`, `steps: list[TestStep] = []`, `expected_outcomes: list[ExpectedOutcome] = []`, `target_app: str | None = None`, `approval_mode: ApprovalMode = ON_RISK`, `risk_flags: list[str] = []`, `confidence: float = 0.0`, `needs_confirmation: bool = True`.
  - `TaskIntakeResult` gains `test_case: TestCase | None = None`.

- [ ] **Step 1: Write the failing model test**

Create `MobiFlow_Agent/tests/intake/test_testcase_models.py`:

```python
from mobiflow_agent.common.contracts import ApprovalMode, VerificationPredicateOperator
from mobiflow_agent.intake.models import (
    AssertionPredicate,
    ExpectedOutcome,
    OutcomeOrigin,
    TestCase,
    TestStep,
)


def test_assertion_predicate_aliases_crown_operator_vocabulary() -> None:
    assert {member.value for member in AssertionPredicate} == {
        member.value for member in VerificationPredicateOperator
    }


def test_testcase_builds_with_expected_outcome_and_defaults() -> None:
    case = TestCase(
        case_id="case-logout",
        raw_goal="Log out and confirm the login button disappears.",
        normalized_goal="Log out and confirm the login button disappears.",
        steps=[TestStep(raw_text="Tap the logout button", hint_action="mobile.tap")],
        expected_outcomes=[
            ExpectedOutcome(
                raw_text="Login button is gone",
                predicate=AssertionPredicate.NOT_EXISTS,
                observation_fact_id="simulated_ui_tree",
                field_path="value[].node_id",
                confidence=0.9,
            )
        ],
    )

    assert case.approval_mode == ApprovalMode.ON_RISK
    assert case.needs_confirmation is True
    assert case.expected_outcomes[0].origin == OutcomeOrigin.MODEL_SYNTHESIZED
    assert case.expected_outcomes[0].expected_value is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/intake/test_testcase_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'AssertionPredicate'`.

- [ ] **Step 3: Add the new models**

Append to `MobiFlow_Agent/mobiflow_agent/intake/models.py` (imports `Any`, `Enum`, `Field`, `ApprovalMode`, `StrictModel` already present at top of file):

```python
class AssertionPredicate(str, Enum):
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    EQUALS = "equals"
    CONTAINS = "contains"
    ANY_EQUALS = "any_equals"
    ANY_CONTAINS = "any_contains"


class OutcomeOrigin(str, Enum):
    MODEL_SYNTHESIZED = "model_synthesized"
    USER_AUTHORED = "user_authored"
    TEMPLATE = "template"


class ExpectedOutcome(StrictModel):
    raw_text: str = Field(min_length=1)
    predicate: AssertionPredicate
    observation_fact_id: str | None = None
    field_path: str = Field(min_length=1)
    expected_value: Any | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    origin: OutcomeOrigin = OutcomeOrigin.MODEL_SYNTHESIZED


class TestStep(StrictModel):
    raw_text: str = Field(min_length=1)
    hint_action: str | None = None


class TestCase(StrictModel):
    case_id: str = Field(min_length=1)
    raw_goal: str = Field(min_length=1)
    normalized_goal: str = Field(min_length=1)
    steps: list[TestStep] = Field(default_factory=list)
    expected_outcomes: list[ExpectedOutcome] = Field(default_factory=list)
    target_app: str | None = None
    approval_mode: ApprovalMode = ApprovalMode.ON_RISK
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_confirmation: bool = True
```

- [ ] **Step 4: Add `test_case` field to `TaskIntakeResult`**

In `MobiFlow_Agent/mobiflow_agent/intake/models.py`, add the field to `TaskIntakeResult` (after `spec`):

```python
class TaskIntakeResult(StrictModel):
    status: TaskIntakeStatus
    spec: TaskIntakeSpec | None = None
    test_case: "TestCase | None" = None
    session: TaskSession | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
```

Note: `TestCase` is defined later in the same module, so the annotation is a forward reference string; pydantic v2 resolves it at class build because both live in one module. If a `NameError` occurs at import, move the five new classes ABOVE `TaskIntakeResult`.

- [ ] **Step 5: Extend `__all__`**

In `MobiFlow_Agent/mobiflow_agent/intake/models.py`, add the new names to `__all__`:

```python
__all__ = [
    "AssertionPredicate",
    "ExpectedOutcome",
    "OutcomeOrigin",
    "TaskIntakeResult",
    "TaskIntakeSpec",
    "TaskIntakeStatus",
    "TaskIntakeValidationResult",
    "TestCase",
    "TestStep",
]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/intake/test_testcase_models.py -v`
Expected: PASS (both tests).

- [ ] **Step 7: Commit**

```bash
git add mobiflow_agent/intake/models.py tests/intake/test_testcase_models.py
git commit -m "feat(intake): add TestCase domain model and predicate alias enum"
```

---

## Task 3: `TestCaseParser` (prose → `TestCase` draft)

**Files:**
- Modify: `MobiFlow_Agent/mobiflow_agent/intake/prompting.py` (add `TestCaseParserPromptBuilder`)
- Modify: `MobiFlow_Agent/mobiflow_agent/intake/interpreter.py` (add `TestCaseParser`)
- Test: `MobiFlow_Agent/tests/intake/test_testcase_parser.py`

**Interfaces:**
- Consumes: `TestCase` (Task 2), `ModelRuntime.generate_structured` (runtime.py:142-150 — kwargs `role`, `prompt`, `response_model`, `profile_name`, `metadata`; returns object with `.output` and `.response.trace.invocation_id`), `AgentRole.TASK_INTERPRETER` (agents/contracts.py:14), `ScenarioTemplateRegistry.visible_templates()` (templates.py:83).
- Produces: `TestCaseParser(model_runtime=None, prompt_builder=None, template_registry=None)` with `parse(raw_goal, *, platform_context=None, profile_name=None) -> TaskIntakeResult`. On success: `status=READY`, `test_case` set, `trace_refs=[invocation_id]`. On model error / no runtime: `status=NEEDS_CLARIFICATION` + a question (NO template admission gate).

- [ ] **Step 1: Write the failing parser tests**

Create `MobiFlow_Agent/tests/intake/test_testcase_parser.py`:

```python
from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.intake.interpreter import TestCaseParser
from mobiflow_agent.intake.models import AssertionPredicate, TaskIntakeStatus, TestCase
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient


def _runtime(*responses) -> ModelRuntime:
    return ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="intake-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=list(responses))},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.TASK_INTERPRETER.value: "intake-profile"}),
    )


def test_parser_returns_ready_testcase_from_model_output() -> None:
    draft = TestCase(
        case_id="case-logout",
        raw_goal="Log out and confirm the login button disappears.",
        normalized_goal="Log out and confirm the login button disappears.",
        expected_outcomes=[],
    )
    parser = TestCaseParser(model_runtime=_runtime(draft))

    result = parser.parse("Log out and confirm the login button disappears.")

    assert result.status == TaskIntakeStatus.READY
    assert result.test_case is not None
    assert result.test_case.case_id == "case-logout"
    assert result.trace_refs


def test_parser_returns_clarification_on_model_failure() -> None:
    parser = TestCaseParser(model_runtime=_runtime(ValueError("boom")))

    result = parser.parse("something unparseable")

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.test_case is None
    assert result.clarification_questions


def test_parser_without_runtime_asks_for_clarification_not_template_gate() -> None:
    parser = TestCaseParser(model_runtime=None)

    result = parser.parse("totally novel goal with no template match")

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.test_case is None
    assert "scenario_id" not in result.issues
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/intake/test_testcase_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'TestCaseParser'`.

- [ ] **Step 3: Add the prompt builder**

Append to `MobiFlow_Agent/mobiflow_agent/intake/prompting.py` (`PromptBundle`, `Any` already imported):

```python
class TestCaseParserPromptBuilder:
    def build(
        self,
        *,
        raw_goal: str,
        scenario_templates: list[dict],
        platform_context: dict[str, Any] | None = None,
    ) -> PromptBundle:
        return PromptBundle(
            system_prompt=(
                "You are the TestCase compiler for MobiFlow Agent. Convert the raw mobile "
                "regression goal into a structured TestCase: a normalized_goal, optional steps, "
                "and one or more expected_outcomes describing what must be observed to pass. "
                "The provided scenario_templates are few-shot examples only, not a closed list; "
                "if none match, still produce a faithful TestCase. Do not invent devices or actions "
                "outside the platform_context. Return only the structured TestCase."
            ),
            context_payload={
                "raw_goal": raw_goal,
                "scenario_templates": scenario_templates,
                "platform_context": platform_context or {},
            },
            preserve_keys=["raw_goal", "scenario_templates", "platform_context"],
            metadata={"prompt_kind": "testcase_parser"},
        )
```

Then extend `__all__` in that file: `__all__ = ["TaskInterpreterPromptBuilder", "TestCaseParserPromptBuilder"]`.

- [ ] **Step 4: Add the `TestCaseParser`**

Append to `MobiFlow_Agent/mobiflow_agent/intake/interpreter.py` and update its imports. Add `TestCase` and `TaskIntakeStatus` to the existing `.models` import, and import the new prompt builder:

```python
from .models import TaskIntakeResult, TaskIntakeSpec, TaskIntakeStatus, TestCase
from .prompting import TaskInterpreterPromptBuilder, TestCaseParserPromptBuilder
```

```python
class TestCaseParser:
    def __init__(
        self,
        *,
        model_runtime: ModelRuntime | None = None,
        prompt_builder: TestCaseParserPromptBuilder | None = None,
        template_registry: ScenarioTemplateRegistry | None = None,
    ) -> None:
        self._model_runtime = model_runtime
        self._prompt_builder = prompt_builder or TestCaseParserPromptBuilder()
        self._template_registry = template_registry or ScenarioTemplateRegistry.default()

    def parse(
        self,
        raw_goal: str,
        *,
        platform_context: dict[str, Any] | None = None,
        profile_name: str | None = None,
    ) -> TaskIntakeResult:
        if self._model_runtime is None:
            return self._clarification("需要模型运行时来把自然语言目标编译成 TestCase。")
        prompt = self._prompt_builder.build(
            raw_goal=raw_goal,
            scenario_templates=self._template_registry.visible_templates(),
            platform_context=platform_context or {},
        )
        try:
            generated = self._model_runtime.generate_structured(
                role=AgentRole.TASK_INTERPRETER,
                prompt=prompt,
                response_model=TestCase,
                profile_name=profile_name,
                metadata={"raw_goal": raw_goal},
            )
        except Exception:
            return self._clarification("无法把该目标解析为 TestCase，请补充更明确的描述。")
        return TaskIntakeResult(
            status=TaskIntakeStatus.READY,
            test_case=generated.output,
            trace_refs=[generated.response.trace.invocation_id],
        )

    @staticmethod
    def _clarification(question: str) -> TaskIntakeResult:
        return TaskIntakeResult(
            status=TaskIntakeStatus.NEEDS_CLARIFICATION,
            clarification_questions=[question],
        )
```

Update `__all__` at the bottom of `interpreter.py`: `__all__ = ["TaskInterpreter", "TestCaseParser"]`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/intake/test_testcase_parser.py -v`
Expected: PASS (all three tests).

- [ ] **Step 6: Commit**

```bash
git add mobiflow_agent/intake/prompting.py mobiflow_agent/intake/interpreter.py tests/intake/test_testcase_parser.py
git commit -m "feat(intake): add TestCaseParser compiling prose into TestCase drafts"
```

---

## Task 4: `TestCaseValidator` (structural legality only)

**Files:**
- Modify: `MobiFlow_Agent/mobiflow_agent/intake/validation.py` (add `TestCaseValidator`)
- Test: `MobiFlow_Agent/tests/intake/test_testcase_validator.py`

**Interfaces:**
- Consumes: `TestCase` (Task 2), `TaskIntakeValidationResult` (models.py:46-49 — `accepted`, `issues`, `clarification_questions`), `DEFAULT_MOBILE_ACTIONS` (templates.py:10), `AssertionPredicate` (Task 2).
- Produces: `TestCaseValidator(allowed_actions=None)` with `validate(test_case, *, confirmed=False) -> TaskIntakeValidationResult`. Pure structural (no model call), mirrors `StepPolicyDecisionValidator`.
- Checks: `normalized_goal` non-empty; ≥1 `expected_outcome` (else `missing_expected_outcome`); each `TestStep.hint_action` (when set) ∈ `DEFAULT_MOBILE_ACTIONS` (else `disallowed_action:<x>`); each `ExpectedOutcome.predicate` ∈ `AssertionPredicate` (guaranteed by enum typing — the check is defensive); risk gate: `risk_flags` and `needs_confirmation` and not `confirmed` ⇒ `confirmation_required`. NONE of the three deleted equality-lock checks (`target_id`, `verification_template`, `has_verification_template`).

- [ ] **Step 1: Write the failing validator tests**

Create `MobiFlow_Agent/tests/intake/test_testcase_validator.py`:

```python
from mobiflow_agent.intake.models import AssertionPredicate, ExpectedOutcome, TestCase, TestStep
from mobiflow_agent.intake.validation import TestCaseValidator


def _outcome() -> ExpectedOutcome:
    return ExpectedOutcome(
        raw_text="Home screen is visible",
        predicate=AssertionPredicate.EQUALS,
        observation_fact_id="simulated_screen_snapshot",
        field_path="value.title",
        expected_value="Home Screen",
        confidence=0.9,
    )


def test_validator_accepts_structurally_legal_case() -> None:
    case = TestCase(
        case_id="case-1",
        raw_goal="Login and reach home.",
        normalized_goal="Login and reach home.",
        steps=[TestStep(raw_text="Tap login", hint_action="mobile.tap")],
        expected_outcomes=[_outcome()],
        needs_confirmation=False,
    )

    result = TestCaseValidator().validate(case)

    assert result.accepted is True
    assert result.issues == []


def test_validator_rejects_case_without_expected_outcome() -> None:
    case = TestCase(
        case_id="case-2",
        raw_goal="Do something.",
        normalized_goal="Do something.",
        expected_outcomes=[],
        needs_confirmation=False,
    )

    result = TestCaseValidator().validate(case)

    assert result.accepted is False
    assert "missing_expected_outcome" in result.issues
    assert result.clarification_questions


def test_validator_rejects_disallowed_hint_action() -> None:
    case = TestCase(
        case_id="case-3",
        raw_goal="Login.",
        normalized_goal="Login.",
        steps=[TestStep(raw_text="Run a shell", hint_action="mobile.shell")],
        expected_outcomes=[_outcome()],
        needs_confirmation=False,
    )

    result = TestCaseValidator().validate(case)

    assert result.accepted is False
    assert "disallowed_action:mobile.shell" in result.issues


def test_validator_preserves_risk_confirmation_gate() -> None:
    case = TestCase(
        case_id="case-4",
        raw_goal="Delete account.",
        normalized_goal="Delete the simulated account.",
        expected_outcomes=[_outcome()],
        risk_flags=["destructive_action"],
        needs_confirmation=True,
    )

    blocked = TestCaseValidator().validate(case, confirmed=False)
    confirmed = TestCaseValidator().validate(case, confirmed=True)

    assert blocked.accepted is False
    assert "confirmation_required" in blocked.issues
    assert confirmed.accepted is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/intake/test_testcase_validator.py -v`
Expected: FAIL — `ImportError: cannot import name 'TestCaseValidator'`.

- [ ] **Step 3: Add the `TestCaseValidator`**

Append to `MobiFlow_Agent/mobiflow_agent/intake/validation.py`. Add imports at the top of the file:

```python
from .models import TaskIntakeSpec, TaskIntakeValidationResult, TestCase
from .templates import DEFAULT_MOBILE_ACTIONS, ScenarioTemplateRegistry
```

```python
class TestCaseValidator:
    def __init__(self, *, allowed_actions: set[str] | None = None) -> None:
        self._allowed_actions = allowed_actions or set(DEFAULT_MOBILE_ACTIONS)

    def validate(self, test_case: TestCase, *, confirmed: bool = False) -> TaskIntakeValidationResult:
        issues: list[str] = []
        questions: list[str] = []

        if not test_case.normalized_goal.strip():
            issues.append("missing_normalized_goal")
        if not test_case.expected_outcomes:
            issues.append("missing_expected_outcome")
            questions.append("这个测试用例的预期结果是什么？")

        for step in test_case.steps:
            if step.hint_action is not None and step.hint_action not in self._allowed_actions:
                issues.append(f"disallowed_action:{step.hint_action}")

        if test_case.risk_flags and test_case.needs_confirmation and not confirmed:
            issues.append("confirmation_required")
            questions.append("该用例包含高风险操作，需要显式确认后才能创建执行 session。")

        normalized_issues = self._dedupe(issues)
        return TaskIntakeValidationResult(
            accepted=not normalized_issues,
            issues=normalized_issues,
            clarification_questions=self._dedupe(questions),
        )

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped
```

Update `__all__` at the bottom of `validation.py`: `__all__ = ["TaskIntakeValidator", "TestCaseValidator"]`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/intake/test_testcase_validator.py -v`
Expected: PASS (all four tests).

- [ ] **Step 5: Commit**

```bash
git add mobiflow_agent/intake/validation.py tests/intake/test_testcase_validator.py
git commit -m "feat(intake): add structural TestCaseValidator without template equality lock"
```

---

## Task 5: `AssertionSynthesizer` (ExpectedOutcome → VerificationCheck)

**Files:**
- Modify: `MobiFlow_Agent/mobiflow_agent/intake/prompting.py` (add `AssertionSynthesizerPromptBuilder`)
- Create: `MobiFlow_Agent/mobiflow_agent/intake/synthesizer.py`
- Test: `MobiFlow_Agent/tests/intake/test_assertion_synthesizer.py`

**Interfaces:**
- Consumes: `ExpectedOutcome`, `TestCase` (Task 2); `ModelRuntime.generate_structured`; `AgentRole.TASK_INTERPRETER`; `VerificationCheck`, `VerificationPredicate`, `VerificationPredicateOperator` (contracts.py).
- Produces:
  - `SynthesizedAssertion(StrictModel)`: `check_id: str`, `description: str`, `evidence_hint: str | None = None`, `predicates: list[VerificationPredicate] = []`. (Intake-internal; not a crown contract.)
  - `AssertionSynthesisResult`: `accepted: bool`, `checks: list[VerificationCheck] = []`, `clarification_questions: list[str] = []`, `issues: list[str] = []`, `trace_refs: list[str] = []`.
  - `AssertionSynthesizer(model_runtime, prompt_builder=None, allowed_fact_ids=None)` with `synthesize(test_case) -> AssertionSynthesisResult`.
- Phase-1 fact catalog (allowed `fact_id`s, per G5): `{"mobile_observation_summary", "simulated_screen_snapshot", "simulated_ui_tree"}`.
- Synthesis validator rejects a predicate when: `operator ∉ VerificationPredicateOperator` (defensive; enum-typed), `field_path` empty, or `fact_id ∉` catalog (a `None` fact_id is also rejected — every gating predicate must anchor to a catalog fact). An assertion with ZERO valid predicates is a synthesis failure. One retry feeding the violation back; second failure → clarification. NO deterministic template fast-path (YAGNI). `evidence_hint` is context only, never the sole matcher.

- [ ] **Step 1: Write the failing synthesizer tests**

Create `MobiFlow_Agent/tests/intake/test_assertion_synthesizer.py`:

```python
from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import VerificationPredicate, VerificationPredicateOperator
from mobiflow_agent.intake.models import AssertionPredicate, ExpectedOutcome, TestCase
from mobiflow_agent.intake.synthesizer import AssertionSynthesizer, SynthesizedAssertion
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient


def _runtime(*responses) -> ModelRuntime:
    return ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="intake-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=list(responses))},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.TASK_INTERPRETER.value: "intake-profile"}),
    )


def _case_with_one_outcome() -> TestCase:
    return TestCase(
        case_id="case-home",
        raw_goal="Reach home.",
        normalized_goal="Reach home.",
        expected_outcomes=[
            ExpectedOutcome(
                raw_text="Home screen is visible",
                predicate=AssertionPredicate.EQUALS,
                observation_fact_id="simulated_screen_snapshot",
                field_path="value.title",
                expected_value="Home Screen",
                confidence=0.9,
            )
        ],
    )


def test_synthesizer_builds_verification_check_from_valid_model_output() -> None:
    good = SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        evidence_hint="Home Screen",
        predicates=[
            VerificationPredicate(
                fact_id="simulated_screen_snapshot",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )
    synthesizer = AssertionSynthesizer(model_runtime=_runtime(good))

    result = synthesizer.synthesize(_case_with_one_outcome())

    assert result.accepted is True
    assert len(result.checks) == 1
    assert result.checks[0].check_id == "home-screen-visible"
    assert result.checks[0].predicates[0].fact_id == "simulated_screen_snapshot"


def test_synthesizer_rejects_unknown_fact_id_then_retries_and_succeeds() -> None:
    bad = SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        predicates=[
            VerificationPredicate(
                fact_id="totally_made_up_fact",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )
    good = SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        predicates=[
            VerificationPredicate(
                fact_id="simulated_screen_snapshot",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )
    synthesizer = AssertionSynthesizer(model_runtime=_runtime(bad, good))

    result = synthesizer.synthesize(_case_with_one_outcome())

    assert result.accepted is True
    assert result.checks[0].predicates[0].fact_id == "simulated_screen_snapshot"


def test_synthesizer_clarifies_when_no_valid_predicate_after_retry() -> None:
    empty = SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        evidence_hint="Home Screen",
        predicates=[],
    )
    synthesizer = AssertionSynthesizer(model_runtime=_runtime(empty, empty))

    result = synthesizer.synthesize(_case_with_one_outcome())

    assert result.accepted is False
    assert result.checks == []
    assert result.clarification_questions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/intake/test_assertion_synthesizer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mobiflow_agent.intake.synthesizer'`.

- [ ] **Step 3: Add the prompt builder**

Append to `MobiFlow_Agent/mobiflow_agent/intake/prompting.py`:

```python
class AssertionSynthesizerPromptBuilder:
    def build(
        self,
        *,
        outcome_text: str,
        allowed_fact_ids: list[str],
        allowed_operators: list[str],
        violation: str | None = None,
    ) -> PromptBundle:
        return PromptBundle(
            system_prompt=(
                "You synthesize a single verification check for one expected outcome of a mobile "
                "regression test. Emit at least one structured predicate. Each predicate.operator MUST "
                "be one of allowed_operators; each predicate.fact_id MUST be one of allowed_fact_ids; "
                "field_path must be non-empty (e.g. 'value.title' or 'value[].node_id'). For a "
                "not_exists predicate, anchor fact_id to a screen fact that is reliably observed so "
                "you test 'absent on a screen we DID observe'. evidence_hint is human context only and "
                "must never be the sole matcher. Return only the structured assertion."
            ),
            context_payload={
                "outcome_text": outcome_text,
                "allowed_fact_ids": allowed_fact_ids,
                "allowed_operators": allowed_operators,
                "previous_violation": violation or "",
            },
            preserve_keys=["outcome_text", "allowed_fact_ids", "allowed_operators", "previous_violation"],
            metadata={"prompt_kind": "assertion_synthesizer"},
        )
```

Extend `__all__`: `__all__ = ["AssertionSynthesizerPromptBuilder", "TaskInterpreterPromptBuilder", "TestCaseParserPromptBuilder"]`.

- [ ] **Step 4: Create the synthesizer module**

Create `MobiFlow_Agent/mobiflow_agent/intake/synthesizer.py`:

```python
from __future__ import annotations

from pydantic import Field

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import (
    StrictModel,
    VerificationCheck,
    VerificationPredicate,
    VerificationPredicateOperator,
)
from mobiflow_agent.model.runtime import ModelRuntime

from .models import ExpectedOutcome, TestCase
from .prompting import AssertionSynthesizerPromptBuilder

PHASE_1_FACT_CATALOG = frozenset(
    {"mobile_observation_summary", "simulated_screen_snapshot", "simulated_ui_tree"}
)


class SynthesizedAssertion(StrictModel):
    check_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_hint: str | None = None
    predicates: list[VerificationPredicate] = Field(default_factory=list)


class AssertionSynthesisResult(StrictModel):
    accepted: bool
    checks: list[VerificationCheck] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)


class AssertionSynthesizer:
    def __init__(
        self,
        *,
        model_runtime: ModelRuntime | None = None,
        prompt_builder: AssertionSynthesizerPromptBuilder | None = None,
        allowed_fact_ids: frozenset[str] | None = None,
        profile_name: str | None = None,
    ) -> None:
        self._model_runtime = model_runtime
        self._prompt_builder = prompt_builder or AssertionSynthesizerPromptBuilder()
        self._allowed_fact_ids = allowed_fact_ids or PHASE_1_FACT_CATALOG
        self._profile_name = profile_name

    def synthesize(self, test_case: TestCase) -> AssertionSynthesisResult:
        if self._model_runtime is None:
            return AssertionSynthesisResult(
                accepted=False,
                clarification_questions=["需要模型运行时来合成断言。"],
            )
        checks: list[VerificationCheck] = []
        trace_refs: list[str] = []
        for outcome in test_case.expected_outcomes:
            synthesized, refs, violation = self._synthesize_one(outcome)
            trace_refs.extend(refs)
            if synthesized is None:
                return AssertionSynthesisResult(
                    accepted=False,
                    issues=[violation or "assertion_synthesis_failed"],
                    clarification_questions=[
                        f"无法为预期结果生成可校验断言：{outcome.raw_text}。请补充更明确的可观察条件。"
                    ],
                    trace_refs=trace_refs,
                )
            checks.append(synthesized)
        return AssertionSynthesisResult(accepted=True, checks=checks, trace_refs=trace_refs)

    def _synthesize_one(
        self, outcome: ExpectedOutcome
    ) -> tuple[VerificationCheck | None, list[str], str | None]:
        refs: list[str] = []
        violation: str | None = None
        for attempt in range(2):
            prompt = self._prompt_builder.build(
                outcome_text=outcome.raw_text,
                allowed_fact_ids=sorted(self._allowed_fact_ids),
                allowed_operators=[op.value for op in VerificationPredicateOperator],
                violation=violation,
            )
            try:
                generated = self._model_runtime.generate_structured(
                    role=AgentRole.TASK_INTERPRETER,
                    prompt=prompt,
                    response_model=SynthesizedAssertion,
                    profile_name=self._profile_name,
                    metadata={"outcome_text": outcome.raw_text, "attempt": attempt},
                )
            except Exception:
                violation = "model_error"
                continue
            refs.append(generated.response.trace.invocation_id)
            violation = self._validate(generated.output)
            if violation is None:
                return self._to_check(generated.output), refs, None
        return None, refs, violation

    def _validate(self, assertion: SynthesizedAssertion) -> str | None:
        if not assertion.predicates:
            return "no_predicate"
        for predicate in assertion.predicates:
            if predicate.operator not in VerificationPredicateOperator:
                return f"illegal_operator:{predicate.operator}"
            if not predicate.field_path.strip():
                return "empty_field_path"
            if predicate.fact_id is None or predicate.fact_id not in self._allowed_fact_ids:
                return f"unknown_fact_id:{predicate.fact_id}"
        return None

    @staticmethod
    def _to_check(assertion: SynthesizedAssertion) -> VerificationCheck:
        return VerificationCheck(
            check_id=assertion.check_id,
            description=assertion.description,
            evidence_hint=assertion.evidence_hint,
            predicates=list(assertion.predicates),
        )


__all__ = [
    "AssertionSynthesisResult",
    "AssertionSynthesizer",
    "PHASE_1_FACT_CATALOG",
    "SynthesizedAssertion",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/intake/test_assertion_synthesizer.py -v`
Expected: PASS (all three tests).

- [ ] **Step 6: Commit**

```bash
git add mobiflow_agent/intake/prompting.py mobiflow_agent/intake/synthesizer.py tests/intake/test_assertion_synthesizer.py
git commit -m "feat(intake): add AssertionSynthesizer with vocab-guarded single retry"
```

---

## Task 6: `TestCaseAssembler` (TestCase → VerificationSpec + session args)

**Files:**
- Create: `MobiFlow_Agent/mobiflow_agent/intake/assembler.py`
- Test: `MobiFlow_Agent/tests/intake/test_testcase_assembler.py`

**Interfaces:**
- Consumes: `TestCase` (Task 2), `list[VerificationCheck]` (Task 5 output), `EntityKind`, `VerificationSpec` (contracts.py:190-202, `@model_validator` requires ≥1 `success_checks`).
- Produces:
  - `SessionAssembly(StrictModel)`: `goal: str`, `target_kind: EntityKind`, `target_id: str`, `verification_spec: VerificationSpec`.
  - `TestCaseAssembler` with `assemble(test_case, success_checks) -> SessionAssembly`.
  - `verification_id = f"verification:{target_kind.value}:{target_id}:testcase"`, `target_kind=EntityKind.TASK`, `target_id=test_case.case_id`, `goal=test_case.normalized_goal`.
- These map directly onto `runtime.create_session(goal, target_kind=..., target_id=..., verification_spec=..., session_id=...)` (session_support.py:73-94).

- [ ] **Step 1: Write the failing assembler tests**

Create `MobiFlow_Agent/tests/intake/test_testcase_assembler.py`:

```python
import pytest

from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationPredicate,
    VerificationPredicateOperator,
)
from mobiflow_agent.intake.assembler import SessionAssembly, TestCaseAssembler
from mobiflow_agent.intake.models import TestCase


def _case() -> TestCase:
    return TestCase(
        case_id="case-home",
        raw_goal="Reach home.",
        normalized_goal="Login and reach the home screen.",
        expected_outcomes=[],
    )


def _check() -> VerificationCheck:
    return VerificationCheck(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        predicates=[
            VerificationPredicate(
                fact_id="simulated_screen_snapshot",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )


def test_assembler_produces_testcase_shaped_spec() -> None:
    assembly = TestCaseAssembler().assemble(_case(), [_check()])

    assert isinstance(assembly, SessionAssembly)
    assert assembly.goal == "Login and reach the home screen."
    assert assembly.target_kind == EntityKind.TASK
    assert assembly.target_id == "case-home"
    assert assembly.verification_spec.verification_id == "verification:task:case-home:testcase"
    assert assembly.verification_spec.success_checks == [_check()]


def test_assembler_rejects_empty_success_checks() -> None:
    with pytest.raises(ValueError):
        TestCaseAssembler().assemble(_case(), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/intake/test_testcase_assembler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mobiflow_agent.intake.assembler'`.

- [ ] **Step 3: Create the assembler module**

Create `MobiFlow_Agent/mobiflow_agent/intake/assembler.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/intake/test_testcase_assembler.py -v`
Expected: PASS (both tests; the empty-checks case raises inside the assembler guard before `VerificationSpec` construction).

- [ ] **Step 5: Commit**

```bash
git add mobiflow_agent/intake/assembler.py tests/intake/test_testcase_assembler.py
git commit -m "feat(intake): add TestCaseAssembler translating TestCase to VerificationSpec"
```

---

## Task 7: `submit_test_case` orchestration + exports + README

**Files:**
- Modify: `MobiFlow_Agent/mobiflow_agent/intake/service.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/intake/__init__.py`
- Modify: `MobiFlow_Agent/README.md`
- Test: `MobiFlow_Agent/tests/intake/test_submit_test_case.py` (created here; extended in Task 8)

**Interfaces:**
- Consumes: `TestCaseParser` (Task 3), `TestCaseValidator` (Task 4), `AssertionSynthesizer` (Task 5), `TestCaseAssembler` (Task 6), `TaskGraphRuntime.create_session` (session_support.py:73-94).
- Produces: `TaskIntakeService.submit_test_case(test_case_text, *, platform_context=None, confirmed=False, session_id=None) -> TaskIntakeResult`. `create_session_from_text(raw_goal, ...)` stays as the existing template-based path (unchanged) so its four legacy tests keep passing; the docstring notes `submit_test_case` is the new NL entry point.
- Orchestration order: parse → (clarify on failure) → validate → (clarify on failure) → synthesize → (clarify on failure) → assemble → `create_session` → `READY` result carrying `test_case`, `session`, and accumulated `trace_refs`.

- [ ] **Step 1: Write the failing service test (back-compat + orchestration)**

Create `MobiFlow_Agent/tests/intake/test_submit_test_case.py`:

```python
from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import VerificationPredicate, VerificationPredicateOperator
from mobiflow_agent.intake.interpreter import TestCaseParser
from mobiflow_agent.intake.models import AssertionPredicate, ExpectedOutcome, TaskIntakeStatus, TestCase
from mobiflow_agent.intake.service import TaskIntakeService
from mobiflow_agent.intake.synthesizer import AssertionSynthesizer, SynthesizedAssertion
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient


def _runtime(*responses) -> ModelRuntime:
    return ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="intake-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=list(responses))},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.TASK_INTERPRETER.value: "intake-profile"}),
    )


def _home_case() -> TestCase:
    return TestCase(
        case_id="case-home",
        raw_goal="Login and reach home.",
        normalized_goal="Login and reach the home screen.",
        expected_outcomes=[
            ExpectedOutcome(
                raw_text="Home screen is visible",
                predicate=AssertionPredicate.EQUALS,
                observation_fact_id="simulated_screen_snapshot",
                field_path="value.title",
                expected_value="Home Screen",
                confidence=0.9,
            )
        ],
        needs_confirmation=False,
    )


def _home_assertion() -> SynthesizedAssertion:
    return SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        evidence_hint="Home Screen",
        predicates=[
            VerificationPredicate(
                fact_id="simulated_screen_snapshot",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )


def test_create_session_from_text_still_uses_template_path() -> None:
    result = TaskIntakeService().create_session_from_text(
        "Login to the demo app and reach home screen."
    )

    assert result.status == TaskIntakeStatus.READY
    assert result.session is not None
    assert result.session.target_id == "dynamic_login_success"


def test_submit_test_case_creates_session_with_testcase_spec() -> None:
    parser = TestCaseParser(model_runtime=_runtime(_home_case()))
    synthesizer = AssertionSynthesizer(model_runtime=_runtime(_home_assertion()))
    service = TaskIntakeService(parser=parser, synthesizer=synthesizer)

    result = service.submit_test_case("Login and confirm the home screen is visible.")

    assert result.status == TaskIntakeStatus.READY
    assert result.test_case is not None
    assert result.session is not None
    spec = result.session.initial_verification_spec
    assert spec is not None
    assert spec.verification_id == "verification:task:case-home:testcase"
    assert spec.success_checks[0].check_id == "home-screen-visible"


def test_submit_test_case_clarifies_when_parser_fails() -> None:
    parser = TestCaseParser(model_runtime=_runtime(ValueError("boom")))
    synthesizer = AssertionSynthesizer(model_runtime=_runtime())
    service = TaskIntakeService(parser=parser, synthesizer=synthesizer)

    result = service.submit_test_case("gibberish")

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.session is None
    assert result.clarification_questions
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/intake/test_submit_test_case.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'parser'`.

- [ ] **Step 3: Rewrite `service.py`**

Replace `MobiFlow_Agent/mobiflow_agent/intake/service.py` with:

```python
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
```

- [ ] **Step 4: Run the service tests to verify they pass**

Run: `pytest tests/intake/test_submit_test_case.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: Update intake package exports**

Replace the body of `MobiFlow_Agent/mobiflow_agent/intake/__init__.py` with (adds new symbols, keeps every existing one so `mobiflow_agent/__init__.py` re-exports do not break):

```python
from mobiflow_agent.intake.assembler import SessionAssembly, TestCaseAssembler
from mobiflow_agent.intake.interpreter import TaskInterpreter, TestCaseParser
from mobiflow_agent.intake.models import (
    AssertionPredicate,
    ExpectedOutcome,
    OutcomeOrigin,
    TaskIntakeResult,
    TaskIntakeSpec,
    TaskIntakeStatus,
    TaskIntakeValidationResult,
    TestCase,
    TestStep,
)
from mobiflow_agent.intake.prompting import (
    AssertionSynthesizerPromptBuilder,
    TaskInterpreterPromptBuilder,
    TestCaseParserPromptBuilder,
)
from mobiflow_agent.intake.service import TaskIntakeService
from mobiflow_agent.intake.synthesizer import (
    AssertionSynthesisResult,
    AssertionSynthesizer,
    PHASE_1_FACT_CATALOG,
    SynthesizedAssertion,
)
from mobiflow_agent.intake.templates import DEFAULT_MOBILE_ACTIONS, ScenarioTemplate, ScenarioTemplateRegistry
from mobiflow_agent.intake.validation import TaskIntakeValidator, TestCaseValidator
from mobiflow_agent.intake.verification_factory import VerificationSpecFactory

__all__ = [
    "AssertionPredicate",
    "AssertionSynthesisResult",
    "AssertionSynthesizer",
    "AssertionSynthesizerPromptBuilder",
    "DEFAULT_MOBILE_ACTIONS",
    "ExpectedOutcome",
    "OutcomeOrigin",
    "PHASE_1_FACT_CATALOG",
    "ScenarioTemplate",
    "ScenarioTemplateRegistry",
    "SessionAssembly",
    "SynthesizedAssertion",
    "TaskIntakeResult",
    "TaskIntakeService",
    "TaskIntakeSpec",
    "TaskIntakeStatus",
    "TaskIntakeValidationResult",
    "TaskIntakeValidator",
    "TaskInterpreter",
    "TaskInterpreterPromptBuilder",
    "TestCase",
    "TestCaseAssembler",
    "TestCaseParser",
    "TestCaseParserPromptBuilder",
    "TestCaseValidator",
    "TestStep",
    "VerificationSpecFactory",
]
```

- [ ] **Step 6: Run the full intake + top-level import suite**

Run: `pytest tests/intake -v && python -c "import mobiflow_agent"`
Expected: PASS and clean import (top-level `mobiflow_agent/__init__.py` re-exports the unchanged names it already listed).

- [ ] **Step 7: Update the README**

In `MobiFlow_Agent/README.md`, replace the "Natural Language Intake" body (lines ~88-101) so it documents the new compiler while keeping the template path note:

```markdown
## Natural Language Intake

```python
from mobiflow_agent import TaskIntakeService, TaskGraphRuntime

runtime = TaskGraphRuntime()
intake = TaskIntakeService(runtime=runtime)

# New: compile a natural-language regression TestCase (model-runtime backed).
result = intake.submit_test_case("Log out and confirm the login button disappears.")

# Legacy template-bounded path (still supported):
legacy = intake.create_session_from_text("登录 demo app 并验证进入首页")

if result.session is not None:
    completed = runtime.run(result.session)
```

`submit_test_case` runs the four-stage pipeline (`TestCaseParser → TestCaseValidator → AssertionSynthesizer → TestCaseAssembler`) to compile prose into a `TestCase` and a `VerificationSpec`. Synthesized assertions are confined to the six-member predicate vocabulary (`exists, not_exists, equals, contains, any_equals, any_contains`) over the simulation fact catalog (`mobile_observation_summary`, `simulated_screen_snapshot`, `simulated_ui_tree`); out-of-vocabulary assertions are rejected and retried once before asking for clarification. Real-device observation-fact enrichment is a separate follow-up. `create_session_from_text` remains the template-bounded path for the demo login, permission popup contrast, slow-loading recovery, and approval-required destructive-action scenarios.
```

- [ ] **Step 8: Commit**

```bash
git add mobiflow_agent/intake/service.py mobiflow_agent/intake/__init__.py README.md tests/intake/test_submit_test_case.py
git commit -m "feat(intake): add submit_test_case orchestration and update exports/README"
```

---

## Task 8: Full prose → verdict against the SIMULATION adapter

**Files:**
- Modify: `MobiFlow_Agent/tests/intake/test_submit_test_case.py` (add the end-to-end test)

**Interfaces:**
- Consumes: `TaskIntakeService.submit_test_case` (Task 7), `TaskGraphRuntime` with `ObserverAgent(adapter=...)` + `ExecutorAgent(adapter)` (see `tests/intake/test_task_intake.py:77-97`), `SimulatedMobilePlatformAdapter`, `dynamic_login_success_case()` (fixtures.py:74), model-driven parser + synthesizer via `NoopModelClient`.
- Goal (G5): drive a real prose→`TestCase`→`VerificationSpec`→run→`VERIFIED_SUCCESS` loop against the simulation adapter, whose facts (`simulated_screen_snapshot.value.title == "Home Screen"`) satisfy the synthesized predicate. This proves the synthesized `field_path`/`fact_id` resolve on the simulation fact vocabulary.

- [ ] **Step 1: Write the failing end-to-end test**

Add to `MobiFlow_Agent/tests/intake/test_submit_test_case.py`. Extend the top imports of that file with:

```python
from mobiflow_agent.agents import ExecutorAgent, ObserverAgent
from mobiflow_agent.control import TaskControlPolicy
from mobiflow_agent.evaluation.scenario import dynamic_login_success_case
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.platform.simulation import SimulatedMobilePlatformAdapter
from mobiflow_agent.task import TaskStatus
```

Then add the test (`_runtime`, `_home_assertion` helpers already defined in this file from Task 7):

```python
def test_submit_test_case_runs_full_prose_to_verdict_on_simulation_adapter() -> None:
    case = dynamic_login_success_case()
    adapter = SimulatedMobilePlatformAdapter(case.platform_scenario, target_id=case.scenario_id)
    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(adapter=adapter),
        executor_agent=ExecutorAgent(adapter),
        policy=TaskControlPolicy(allow_recovery=case.allow_recovery),
    )

    parsed_case = TestCase(
        case_id="dynamic_login_success",
        raw_goal="Login to the demo app and confirm the home screen is visible.",
        normalized_goal="Login to the demo app using bounded mobile UI actions.",
        expected_outcomes=[
            ExpectedOutcome(
                raw_text="Home Screen is visible",
                predicate=AssertionPredicate.EQUALS,
                observation_fact_id="simulated_screen_snapshot",
                field_path="value.title",
                expected_value="Home Screen",
                confidence=0.95,
            )
        ],
        needs_confirmation=False,
    )
    service = TaskIntakeService(
        runtime=runtime,
        parser=TestCaseParser(model_runtime=_runtime(parsed_case)),
        synthesizer=AssertionSynthesizer(model_runtime=_runtime(_home_assertion())),
    )

    result = service.submit_test_case("Login to the demo app and confirm the home screen is visible.")
    assert result.status == TaskIntakeStatus.READY
    assert result.session is not None
    assert result.session.initial_verification_spec.target_id == "dynamic_login_success"

    completed = runtime.run(result.session)

    assert completed.status == TaskStatus.COMPLETED
    assert completed.last_verdict is not None
    assert completed.last_verdict.status.value == "verified_success"
```

Note: `case_id` is intentionally set to the scenario id `dynamic_login_success` so the simulation adapter (constructed with `target_id=case.scenario_id`) and the assembled `VerificationSpec.target_id` align; the `value.title == "Home Screen"` predicate resolves against the adapter's `simulated_screen_snapshot` fact.

- [ ] **Step 2: Run the end-to-end test to verify it fails first, then passes**

Run: `pytest "tests/intake/test_submit_test_case.py::test_submit_test_case_runs_full_prose_to_verdict_on_simulation_adapter" -v`
Expected: PASS (all Task 1-7 code is in place; this test is pure composition of shipped units — if it fails, the failure localizes the integration gap, e.g. a target_id mismatch or unresolved field_path).

- [ ] **Step 3: Run the whole suite for regressions**

Run: `pytest -q`
Expected: PASS — all pre-existing tests (including the four legacy `test_task_intake.py` template tests and every `test_verifier_agent.py` case) plus the new intake tests are green.

- [ ] **Step 4: Commit**

```bash
git add tests/intake/test_submit_test_case.py
git commit -m "test(intake): cover full prose-to-verdict path against simulation adapter"
```

---

## Self-Review

- **Spec coverage:** §crown-addition → Task 1; §4 `TestCase` model → Task 2; Stage 1 `TestCaseParser` (drop admission gate) → Task 3; Stage 2 `TestCaseValidator` (delete equality lock, keep risk gate) → Task 4; Stage 3 `AssertionSynthesizer` (§5, vocab guard, single retry, no fast-path, evidence_hint-not-sole-matcher) → Task 5; Stage 4 `TestCaseAssembler` (§spec shape) → Task 6; §8 back-compat (`submit_test_case`, `create_session_from_text` forwarder-equivalent, optional `test_case` field) → Tasks 2 & 7; §9.8 tests incl. G5 simulation e2e → Tasks 1-8. All eight §9 items mapped.
- **Placeholder scan:** every code step shows full code; every run step gives an exact `pytest` command and expected outcome. No TBD/TODO.
- **Type consistency:** `AssertionPredicate`, `OutcomeOrigin`, `ExpectedOutcome`, `TestStep`, `TestCase` (Task 2) are referenced with identical field names in Tasks 3-8; `SynthesizedAssertion`/`AssertionSynthesisResult` (Task 5) consumed unchanged by Task 7; `SessionAssembly` (Task 6) fields (`goal/target_kind/target_id/verification_spec`) map 1:1 to `create_session` kwargs in Task 7. `generate_structured` is always called with the real kwargs (`role`, `prompt`, `response_model`, `profile_name`, `metadata`) and results read via `.output` / `.response.trace.invocation_id`.

## Resolved decisions (finalized by owner during plan review)

These three items were surfaced by the plan author and adjudicated by the owner; they are now binding, not open:

1. **NOT_EXISTS semantics — pin the real (safer) short-circuit behavior.** RESOLVED: the plan is correct and the spec §crown-addition caveat has been corrected to match. `_matches_predicate` (verifier.py:418-430) returns `False` when the anchor `fact_id` is unobserved; absence-of-evidence does NOT read as absence-of-element. Do NOT edit `_matches_predicate` (would exceed G1). Synthesis anchors NOT_EXISTS to a reliably-present fact. Both behaviors pinned by Task 1 Steps 1-7.
2. **`create_session_from_text` stays on the template path this phase.** RESOLVED: keep the legacy template path intact and add `submit_test_case` as the new NL entry (as the plan does). The literal "thin forwarder" collapse from spec §8 is DEFERRED to L2 when the four legacy `test_task_intake.py` template tests are retired — collapsing it now would break them. This staging is the correct "don't dig a hole for the closed loop" tradeoff and is approved.
3. **`case_id` provenance is an L2 concern.** RESOLVED: model-invented `case_id` is acceptable for L0/L1. Caller-supplied / deterministic derivation for the L2 join key is out of scope here; revisit at L2.
