# TestCase Intake Pipeline — L0 + L1 Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:writing-plans to implement this. Steps use checkbox syntax.

> Date: 2026-07-09 · Status: FINAL (reviewed by Plan agent + 2 adversarial reviewers, finalized by owner) · Scope: `MobiFlow_Agent/mobiflow_agent/intake/` + a **bounded** Verifier addition (see G1).

**Goal:** Turn task-intake from a hardcoded-4-scenario template gate into a natural-language **TestCase compiler** — the L0+L1 foundation of MobiFlow's pivot to a natural-language-driven real-device **regression-testing** platform.

**Architecture:** A four-stage intake pipeline (`TestCaseParser → TestCaseValidator → AssertionSynthesizer → TestCaseAssembler`) producing a first-class `TestCase` (goal + expected outcomes), then translating it into the `(TaskSession, VerificationSpec)` the crown layer (Verifier/Recovery/Memory) consumes. Templates demote from admission gate to few-shot seeds.

**Tech Stack:** Python 3.11, pydantic v2 (`StrictModel`, `extra="forbid"`), LangGraph, existing `ModelRuntime.generate_structured`.

---

## Decision log (why this spec differs from the initial sketch)

Two adversarial reviews corrected the draft. The owner's rulings:

- **A1 — break G1 in exactly ONE bounded place: add a `NOT_EXISTS` predicate operator to the Verifier.** Regression suites are saturated with disappearance assertions ("logout → Login button gone", "error banner cleared"). The reviewers proved these are **unrepresentable** today (no negation operator) and that the "positive-successor rewrite" workaround causes **false-PASS** (`EXISTS screen_title=="Home"` passes even while the banner persists). This is a correctness hole in a pass/fail product. So the crown layer's "zero change" rule is itself the structural debt blocking productization — per the positioning baseline's master gate, we remove it. The change is small and symmetric (§Verifier addition).
- **B1 — Phase 1 is SIMULATION-FIRST.** The real-device adapters (`platform/evidence.py:14-19`) emit governance/diagnosis facts (`run_governance_snapshot`, `attempt_diagnosis_bundle`, …) with **no screen content** — synthesized `field_path`s like `value.title` cannot resolve on hardware. That is a separate, deeper gap (the adapter does not surface screen observations). Phase 1 closes the loop against the **simulation adapter**; real-device observation-fact enrichment is a **separately-scoped follow-up**, explicitly out of this spec.

Three corrected factual claims from the draft are folded into the body below (the `required` field is NOT dead; `evidence_hint` fallback MASKS failures; the deterministic template fast-path is cut as YAGNI).

---

## Global Constraints

- **G1 (revised) — Minimal crown change, one operator only.** The ONLY permitted crown-layer edit is adding `NOT_EXISTS` to `VerificationPredicateOperator` and its evaluation branch. `RecoveryAgent`, `Memory`, and the rest of `VerifierAgent` are untouched. Any other crown change is out of scope and must be escalated.
- **G2 — Assertions confined to the (now 6-member) predicate vocabulary.** Synthesized `VerificationCheck.predicates` use only `VerificationPredicateOperator` members. Out-of-vocabulary → reject/retry, never smuggle.
- **G3 — Crown contracts stay `extra="forbid"`.** `VerificationCheck`/`VerificationPredicate`/`VerificationSpec` are `StrictModel` (`contracts.py:9-12`, `166-202`). Do NOT add `origin`/`confidence` to them. All intake-only metadata lives on `TestCase`.
- **G4 — L2/L3 seams preserved.** `TestCase` is the stable input atom; `submit_test_case` takes one case now, a suite later. §7 names the L2 result atom explicitly.
- **G5 — Simulation-first (B1).** Phase 1 correctness is defined and tested against the simulation adapter's fact vocabulary. Real-device fact resolution is a named follow-up, not a Phase-1 acceptance criterion.
- **G6 — Evidence-first.** Every file:line below was verified against real code during review.

---

## Crown-layer addition (the one permitted G1 break)

**File:** `mobiflow_agent/common/contracts.py` + `mobiflow_agent/agents/verifier.py`

1. Add operator: `NOT_EXISTS = "not_exists"` to `VerificationPredicateOperator` (`contracts.py:174-179`).
2. Add the symmetric evaluation branch in `_predicate_values_match` (`verifier.py:454-456`), mirroring `EXISTS`:
   ```python
   if predicate.operator == VerificationPredicateOperator.NOT_EXISTS:
       return not bool(values)
   ```
   `EXISTS` returns `bool(values)`; `NOT_EXISTS` returns `not bool(values)`. `values` is the list resolved from `fact_id` + `field_path` (`verifier.py:418-451`). Empty resolution ⇒ the addressed element is absent ⇒ `NOT_EXISTS` matches.
3. **Semantics caveat (must be in tests) — corrected against real code during planning.** `_matches_predicate` (`verifier.py:418-430`) short-circuits to `False` when NO observed fact matches the specific `predicate.fact_id` (empty `candidate_facts`), *before* `_predicate_values_match` is ever called. So a `NOT_EXISTS` predicate whose anchor `fact_id` was **not observed** evaluates to `False` (does NOT match) — absence-of-evidence does NOT read as absence-of-element. `NOT_EXISTS` matches only when the anchor fact IS present but its `field_path` resolves to nothing. This is the safer behavior (it prevents false-PASS on a screen we never observed), so we keep it as-is — the caveat is NOT to loosen `_matches_predicate` (that would exceed G1). The synthesis prompt (§5) MUST anchor `NOT_EXISTS` predicates to a `fact_id` that is reliably present (e.g. the screen snapshot), so "no such node in a screen we DID observe" is what's tested. Both behaviors are pinned by tests.

---

## The four-stage pipeline

### Stage 1 — `TestCaseParser` (evolves `interpreter.py`)
- **Responsibility:** model parses raw prose → `TestCase` draft. Templates become few-shot examples in the prompt, no longer an admission gate.
- **Input:** `raw_goal: str`, `platform_context`, optional `profile_name`. **Output:** `TestCase` draft + `trace_refs`, or a clarification result.
- **Invocation** (reuse `interpreter.py:57-71`): `model_runtime.generate_structured(role=AgentRole.TASK_INTERPRETER, prompt=..., response_model=TestCase, profile_name=..., metadata={"raw_goal": raw_goal})`; read `generated.output` and `generated.response.trace.invocation_id`. `AgentRole.TASK_INTERPRETER` exists (`agents/contracts.py:14`). Signature confirmed (`model/runtime.py:142-150`).
- **Key change:** today `_fallback_spec` returns `missing_fields=["scenario_id"]` and forces confirmation on no-template-match (`interpreter.py:76-82`). New: **no template match is normal**; only genuine parse failure (model error / unusable output) → clarification.

### Stage 2 — `TestCaseValidator` (rewrite of `validation.py`)
- **Responsibility:** STRUCTURAL legality only. **Delete** the three equality checks that are the real lock: `target_id != template.target_id`, `verification_template != template.verification_template`, `has_verification_template(...)` (`validation.py:23-29`).
- **New checks:** required fields present (`raw_goal`, `normalized_goal`, ≥1 `expected_outcome`); each `TestStep.hint_action` ∈ action allow-list (`DEFAULT_MOBILE_ACTIONS`, `templates.py:10`); each `ExpectedOutcome.predicate` ∈ legal enum; risk gate preserved (`validation.py:36-38`): `risk_flags` + `needs_confirmation` + not `confirmed` ⇒ `confirmation_required`.
- **Pattern:** mirror `StepPolicyDecisionValidator` (`agents/step_policy_validation.py:16-49`) — pure structural issue list, no model call. **Output:** `TaskIntakeValidationResult` (reuse `models.py:46-49`).

### Stage 3 — `AssertionSynthesizer` (new; extracted from `verification_factory.py`) — **L1 core**
- **Responsibility:** each `ExpectedOutcome` → one `VerificationCheck` with legal `predicates`.
- **Single synthesis path (fast-path CUT — YAGNI).** The draft's deterministic template fast-path is dropped; it re-introduced the abandoned gate's dual-path complexity for no Phase-1 benefit. Templates serve only as few-shot prompt seeds.
- **Model path:** `generate_structured` with a constrained response model `SynthesizedAssertion(StrictModel)` = `check_id, description, evidence_hint, predicates: list[VerificationPredicate]`. Then a **synthesis validator** (mirrors `StepPolicyDecisionValidator`) rejects any predicate whose `operator` ∉ enum, `field_path` empty, or `fact_id` ∉ the Phase-1 catalog (§5). Reject → one retry feeding back the specific violation → still bad → clarification.
- **Output:** `list[VerificationCheck]`.

### Stage 4 — `TestCaseAssembler` (new)
- **Responsibility:** thin translation `TestCase` → `(create_session args, VerificationSpec)`.
- **`VerificationSpec` shape** (satisfy `contracts.py:190-202`, ≥1 `success_checks`): `verification_id=f"verification:{target_kind.value}:{target_id}:testcase"`, `target_kind=EntityKind.TASK`, `target_id=case_id`, `success_checks=<synthesized>`.
- **Hand off** via `runtime.create_session(normalized_goal, target_kind=..., target_id=..., verification_spec=..., session_id=...)` — signature unchanged (`graph/session_support.py:73-94`).

---

## 4. The `TestCase` domain model (field-by-field, cross-checked)

All new intake models subclass `StrictModel` in `intake/models.py`.

### `AssertionPredicate` enum — mirrors `VerificationPredicateOperator` + the new operator
`EXISTS, NOT_EXISTS, EQUALS, CONTAINS, ANY_EQUALS, ANY_CONTAINS` — an exact alias of the (post-addition) crown vocab so a translation table can never drift out of vocab (G2). `NOT_EXISTS` is the A1 addition enabling disappearance assertions.

### `ExpectedOutcome`
| field | type | justification / cross-check |
|---|---|---|
| `raw_text` | `str` | source prose; audit + memory reuse |
| `predicate` | `AssertionPredicate` | must be legal enum (G2) |
| `observation_fact_id` | `str \| None` | real `VerificationPredicate.fact_id` selects which `ObservationFact` (`contracts.py:186`) |
| `field_path` | `str` | real addressing: resolved against `fact.model_dump()`, paths start under `value...` (`verifier.py:418-451`; tests use `"value.title"`, `"value[].node_id"`). Corrects sketch's single `target_field`. |
| `expected_value` | `Any \| None` | → `VerificationPredicate.expected`; ignored for `EXISTS`/`NOT_EXISTS` |
| `confidence` | `float 0..1` | **intake-only** (G3); drives §6 gating |
| `origin` | enum `MODEL_SYNTHESIZED / USER_AUTHORED / TEMPLATE` | intake-only provenance for correction + memory reuse |

**Phase-1 fact catalog (simulation, per B1):** `mobile_observation_summary` → `MobileObservationSummary` (`contracts.py:137-143`: `screen_id, screen_title, visible_node_ids[], blocked_state, loading_state, error_state`); `simulated_screen_snapshot` → `value.title`/`value.screen_id`; `simulated_ui_tree` → `value[].node_id`.

### `TestStep` (optional)
| field | type | note |
|---|---|---|
| `raw_text` | `str` | human step |
| `hint_action` | `str \| None` | must be in allow-list; empty steps ⇒ pure dynamic planning |

### `TestCase`
| field | type | note |
|---|---|---|
| `case_id` | `str` | stable id; `VerificationSpec.target_id` seed; L2 suite-membership key |
| `raw_goal` / `normalized_goal` | `str` | mirror `TaskIntakeSpec` (`models.py:19-20`); `normalized_goal` → `create_session` goal |
| `steps` | `list[TestStep]` | optional |
| `expected_outcomes` | `list[ExpectedOutcome]` | **≥1 enforced** by Stage 2 (VerificationSpec needs ≥1 success check, `contracts.py:198-202`) |
| `target_app` | `str \| None` | weak binding now; profile mount-point later (L3) |
| `approval_mode` | `ApprovalMode` | reuse `contracts.py:24-27`; default `ON_RISK` |
| `risk_flags` | `list[str]` | drives confirmation gate |
| `confidence` | `float` | overall parse confidence |
| `needs_confirmation` | `bool` | risk / low-confidence gate |

---

## 5. Assertion synthesis mechanism (L1)

1. **Prompt** the model with: the outcome `raw_text`, the legal 6-operator enum (incl. `NOT_EXISTS` with its "anchor to a present fact_id" rule from the crown-addition caveat), and the **Phase-1 fact catalog** (§4) so it can only reference real simulation observation fields.
2. **Constrained response model** `SynthesizedAssertion` passed as `response_model` to `generate_structured` (same call shape as `interpreter._interpret_with_model`).
3. **Synthesis validator** (mirrors `StepPolicyDecisionValidator`): reject on illegal operator / empty `field_path` / unknown `fact_id` → one retry with the violation fed back → second failure → clarification.
4. **Assemble** validated assertions into `VerificationCheck`s → `VerificationSpec`.
5. **`evidence_hint` — populate but treat as a WEAK, failure-MASKING fallback, not a safety net.** When `predicates` is empty the Verifier falls back to loose casefold-substring / ≥3-char-token matching on evidence_hint/description against ALL observation text (`verifier.py:404-415`, `528-534`), which can **spuriously PASS on the wrong screen**. Therefore: always emit at least one structured predicate; `evidence_hint` is human-readable context only, never the sole matcher for a gating check. An assertion that produced NO valid predicate is a synthesis failure (→ clarification), not a "degrade to evidence_hint" success.

---

## 6. Error / clarification & confidence handling

- **Parse failure** → `NEEDS_CLARIFICATION` + question (not `REJECTED`). Preserves `TaskIntakeResult`/`TaskIntakeStatus` (`models.py:12-43`).
- **Missing expected_outcome** → clarification ("What is the expected result?"); a zero-success-check spec raises at `contracts.py:200`, so catch in Stage 2.
- **Out-of-vocab / no-valid-predicate assertion** → retry once, then clarification.
- **Unconfirmed risk** → preserve gate (`validation.py:36-38`).
- **Low-confidence assertion — corrected mechanism.** The draft claimed `required` is dead; that is FALSE: `step_policy.py:203` reads `check.required` to soft-gate step progression (`_satisfies_active_spec` filters `if check.required`). BUT `verifier.py:242-255` still counts every unmatched `success_check` (required or not) into `unmatched_check_ids`, so a non-required unmatched check yields `VERIFIED_UNKNOWN`, not `SUCCESS`. Net: `required=False` softens step-advance but NOT the final verdict. **Phase-1 rule:** emit only `confidence ≥ threshold` outcomes as gating `success_checks`; below threshold, set `TestCase.needs_confirmation=True` and surface the assertion for tester approval before it becomes a check. Do NOT rely on `required=False` to soft-gate the verdict — it doesn't.

---

## 7. L2/L3 extension seams

- **L2 (suites + regression report):** `submit_test_case(TestCase)` is the atom; add `submit_test_suite(list[TestCase])` later, looping the same four stages. **Named L2 result atom (add at L2, not now):** a `TestRunResult` correlating `(run_id, case_id) → VerificationVerdict` plus suite membership — `TestCase` is input-only and deliberately carries no verdict. `case_id` is the join key. This is ADDITIVE (no rework of stages 1-4); named here so L2 doesn't assume `case_id` alone suffices.
- **L3 (CI webhook + device matrix):** `target_app` is the profile mount-point; `create_session(session_id=...)` already accepts an external id, so CI can drive sessions per (case × device) without touching intake internals.
- **Real-device observation facts (the B1 follow-up):** a prerequisite for L3 on hardware — the real adapter must surface screen-content facts matching the Phase-1 catalog shape. Tracked separately.
- **Templates:** `ScenarioTemplateRegistry` stays as few-shot corpus only; growing it needs no code change.

---

## 8. Backward compatibility

- **New entry:** `TaskIntakeService.submit_test_case(test_case_text: str, *, platform_context=None, confirmed=False, session_id=None) -> TaskIntakeResult`.
- **Keep** `create_session_from_text(raw_goal, ...)` as a thin forwarder → `submit_test_case`.
- **Return shape** stays `TaskIntakeResult`/`TaskIntakeStatus` (`models.py:37-43`); add optional `test_case: TestCase | None` alongside existing `spec` (keep `spec` populated for back-compat).

---

## 9. Decomposition into implementable tasks (rough — plan skill details)

1. Crown addition: `NOT_EXISTS` operator + evaluation branch + caveat tests (`contracts.py`, `verifier.py`).
2. `intake/models.py`: add `TestCase`, `TestStep`, `ExpectedOutcome`, `AssertionPredicate`; optional `test_case` field on `TaskIntakeResult`.
3. `interpreter.py` → `TestCaseParser`: `response_model=TestCase`, templates as few-shot, drop admission-gate fallback.
4. `validation.py` → `TestCaseValidator`: structural checks, drop equality lock.
5. `AssertionSynthesizer` (new): prompt + `SynthesizedAssertion` model + synthesis validator + single-retry (NO template fast-path).
6. `TestCaseAssembler` (new): `TestCase` → `VerificationSpec` + `create_session` args.
7. `service.py`: `submit_test_case` orchestration + `create_session_from_text` forwarder; update `intake/__init__.py` + README.
8. Tests: `NOT_EXISTS` (incl. absence-of-fact caveat), parser, validator, synthesizer vocab-rejection + no-predicate→clarification, assembler spec-shape, service back-compat, and a full prose→verdict path against the **simulation** adapter.

---

## 10. Resolved decisions (was "open questions")

1. **Negation** → RESOLVED A1: add bounded `NOT_EXISTS` operator (crown addition above).
2. **Low-confidence gating** → RESOLVED: `required` is not the lever (it doesn't soften the verdict); use confidence-threshold emission + `needs_confirmation`.
3. **fact_id catalog / real device** → RESOLVED B1: Phase 1 is simulation-first; real-device observation-fact enrichment is a separate follow-up (§7).
