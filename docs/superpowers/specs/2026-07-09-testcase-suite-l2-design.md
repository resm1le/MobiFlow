# TestCase Suite (L2) — Regression Report Design Spec

> Date: 2026-07-09 · Status: FINAL (Plan agent draft + adversarial reviewer, finalized by owner) · Scope: `MobiFlow_Agent/mobiflow_agent/intake/` + a new report renderer. NO production code in this task.
> Branch: `feat/testcase-suite-l2` (from main = merged L0+L1).

## Review corrections folded in (owner rulings on adversarial-review findings)

- **R1 (HIGH, correctness) — outcome mapping keys on `session.status` FIRST, verdict only refines.** `_complete_step_without_verification` (`session_support.py:147-156`) transitions a run to `FAILED` WITHOUT touching `last_verdict`, so a stale `VERIFIED_SUCCESS` could misfire PASSED. FIXED: PASSED requires `session.status == COMPLETED`; see the rewritten §2.1.
- **R2 (MED-HIGH) — mapping must be exhaustive with a catch-all.** `runtime.run` short-circuits on the full terminal set `{COMPLETED, FAILED, AWAITING_APPROVAL, HANDED_OFF}` (`runtime.py:83-89`; `TaskStatus`, `plan.py:10-20`). The draft dropped `HANDED_OFF`. FIXED: §2.1 covers every terminal `TaskStatus` and ends with a catch-all → ERROR (no silent fall-through).
- **R3 (MED) — add a 5th outcome `INCONCLUSIVE`.** Collapsing `VERIFIED_UNKNOWN`/`BLOCKED`/`HANDED_OFF` into FAILED loses the "genuinely failed vs couldn't-determine" distinction a regression report needs. FIXED: `SuiteCaseOutcome` gains `INCONCLUSIVE` (supersedes the earlier 4-outcome ruling). `TestSuiteReport` gains an `inconclusive` count.
- **R4 (MED) — renderer sources from the REDACTED dict.** Markdown/JSON must be built from the `_redact`-ed `model_dump`, never from raw `result.verdict`/`result.summary` (which would bypass redaction). Mandated in §3.
- **R5 (LOW-MED) — determinism injection is partial.** `session_id`/`verdict_id` are still `uuid4`-based (`ids.py:12`), so full-report golden tests are flaky even with injected `run_id`/`clock`. Exporter tests MUST field-mask `session_id`/`verdict_id`/nested verdict ids rather than assert full goldens (§6).

**Goal:** Loop the L0+L1 single-case path (`submit_test_case` → `runtime.run`) over an ordered set of prose test cases, serially with per-case failure isolation, and aggregate a first-class structured `TestSuiteReport` (plus a thin JSON/Markdown renderer). Team-usable minimal closed loop; NO Platform-layer, NO concurrency, NO device fan-out (all L3).

**Architecture:** `TestSuite` (suite_id + ordered prose inputs) → `TestSuiteRunner.run(suite)` loops each case: `TaskIntakeService.submit_test_case(text)` → if READY, `TaskGraphRuntime.run(session)` → map terminal state to a `TestRunResult` → collect → aggregate `TestSuiteReport`. A separate `TestSuiteReportExporter` (mirrors `ExecutionTraceExporter`) projects the report to JSON/Markdown. The structured report is the product; the render is a projection.

---

## Global constraints

- **G-L2-1 — Pure Agent-layer.** L2 lives entirely in `MobiFlow_Agent/`. It composes the existing `TaskIntakeService` + `TaskGraphRuntime` in Python. No Java Platform layer, no device-pool fan-out.
- **G-L2-2 — Serial + failure-isolation.** Cases run one at a time, in submission order. Every case is wrapped in try/except; an intake `NEEDS_CLARIFICATION`, a non-success verdict, or ANY raised exception is recorded into a `TestRunResult` and the batch CONTINUES. A partially-failing suite is the NORMAL case; the batch always runs to completion.
- **G-L2-3 — Structured-report-first.** `TestSuiteReport` / `TestRunResult` are the atoms; the renderer is a pure projection. L3's dashboard/CI consume the structured objects directly, never re-parse Markdown.
- **G-L2-4 — Additive.** The L0+L1 single-case path (`submit_test_case`, `create_session_from_text`, the four stages) is untouched. L2 adds new modules + one new public entry point.
- **G-L2-5 — Evidence-first.** Every field/decision below is cross-checked against real code with file:line.
- **G-L2-6 — run_id determinism.** `run_id` and `generated_at_ms` MUST be injectable for tests (no bare `uuid4()`/`time.time()` inside the runner). Real ids come from an injected factory whose default uses `uuid4`, matching the existing `common/ids.py` pattern (`ids.py:8-13`).

---

## Finalized decisions (owner rulings on the 5 open questions)

1. **AWAITING_APPROVAL** → map to **INCONCLUSIVE** (revised per R3; was ERROR). A batch is non-interactive; a paused case is unrunnable but not an infrastructure error — it belongs with the "couldn't determine" bucket. Summary: "run halted awaiting approval; pass confirmed=True or resolve risk gate".
2. **case_id authority** → `SuiteCaseInput.case_id` (caller-supplied) is the **authoritative** suite-membership / join key. The parser-minted `TestCase.case_id` is NOT used for correlation. Keeps L0+L1 `submit_test_case` untouched (G-L2-4).
3. **Memory determinism** → regression suites default to **`memory_runtime=None`** for reproducibility. Memory-enabled (order-sensitive) runs are allowed but the runner does not configure them; documented as a caller choice.
4. **API boundary** → **standalone `TestSuiteRunner`** composing `(TaskIntakeService, TaskGraphRuntime)`. NOT a method on `TaskIntakeService` (which is a compiler and must not gain execution dependencies). This deviates from spec §7's literal `submit_test_suite` name — accepted.
5. **Trace capture** → `TestRunResult` carries the lightweight **`session_id` + `trace_refs` reference**, not a full per-case `ExecutionTraceExporter` dump. Keeps the report light; the dump is retrievable on demand via session_id.

---

## 1. Domain model

**Placement decision: new module `intake/suite.py`.** `intake/models.py` holds *single-case intake* atoms (`TestCase`, `ExpectedOutcome`, `TaskIntakeResult`, `models.py:37-113`). The L2 atoms are *result/aggregation* atoms with a different lifecycle (post-run, correlate run×case). Keeping them in a dedicated `intake/suite.py` avoids bloating `models.py` and keeps the L0+L1 file diff-clean (G-L2-4). All subclass `StrictModel` (`common/contracts.py`, `extra="forbid"`), consistent with `models.py:8`.

### 1.1 `TestSuite`

Takes **raw prose strings**, not pre-parsed `TestCase`s — justification: parsing/synthesis is per-case and can itself fail per-case (parse failure → clarification, `service.py:80-94`; synthesis failure → clarification, `service.py:96-105`). Accepting prose mirrors `submit_test_case(test_case_text: str, ...)` (`service.py:72-79`) so a per-case parse failure becomes a `CLARIFICATION_BLOCKED` `TestRunResult` inside the same isolation boundary rather than exploding at suite-construction time.

| field | type | justification / cross-check |
|---|---|---|
| `suite_id` | `str` (min_length=1) | stable suite identity; report join field |
| `name` | `str \| None` | human label for the report header |
| `cases` | `list[SuiteCaseInput]` (≥1) | ordered; order = execution order (G-L2-2) |

`SuiteCaseInput`:
| field | type | note |
|---|---|---|
| `case_id` | `str` (min_length=1) | caller-supplied stable id; the authoritative join key (decision #2). MUST be caller-supplied for determinism (G-L2-6) — do NOT derive from the parsed case, since parse can fail before a case_id exists. |
| `text` | `str` (min_length=1) | raw prose fed to `submit_test_case` |
| `platform_context` | `dict[str,Any] \| None` | forwarded to `submit_test_case` (`service.py:76`) |
| `confirmed` | `bool` (default False) | forwarded (`service.py:77`); lets a suite pre-approve risk-gated cases |

### 1.2 `TestRunResult`

| field | type | justification / cross-check |
|---|---|---|
| `run_id` | `str` (min_length=1) | the suite-run identity; correlates `(run_id, case_id)` (spec §7). Injected (G-L2-6). |
| `case_id` | `str` (min_length=1) | `SuiteCaseInput.case_id`; join key (decision #2) |
| `outcome` | `SuiteCaseOutcome` enum | PASSED / FAILED / CLARIFICATION_BLOCKED / ERROR (§2 mapping) |
| `verdict` | `VerificationVerdict \| None` | nullable — absent when the case never ran (CLARIFICATION_BLOCKED) or crashed pre-verdict (ERROR). Real source: `session.last_verdict` (`session.py:42`, type `VerificationVerdict \| None`). |
| `session_id` | `str \| None` | the executed session's id (`session.py:26`); None if intake never produced a session. Lets the report cross-link to a per-session `ExecutionTraceExporter` dump. |
| `session_status` | `TaskStatus \| None` | terminal status of the run (`session.py:28`, values `plan.py:10-20`); None if never ran. Kept for L3/debug even though `outcome` is the product-level projection. |
| `summary` | `str \| None` | short failure/blocked/error message. For FAILED: `verdict.summary` (`contracts.py:224`). For CLARIFICATION_BLOCKED: first of `TaskIntakeResult.clarification_questions`/`issues` (`models.py:42-43`). For ERROR: the exception `str`. |
| `trace_refs` | `list[str]` | the single-run intake trace refs from `TaskIntakeResult.trace_refs` (`models.py:44`, populated `service.py:84,97,119`). This is the "reference to the single-run trace." |

> **`verdict` field cross-check:** `VerificationVerdict.status` is a `VerificationStatus` (`contracts.py:223`) with values VERIFIED_SUCCESS / VERIFIED_FAILED / VERIFIED_UNKNOWN / BLOCKED (`contracts.py:46-50`). `.status.value` is the string. Storing the whole verdict (not just status) lets the report show `matched_check_ids`/`unmatched_check_ids`/`evidence_refs` (`contracts.py:227-229`) for attribution — cheap and additive.

### 1.3 `TestSuiteReport`

| field | type | note |
|---|---|---|
| `run_id` | `str` | shared across all results |
| `suite_id` | `str` | from `TestSuite` |
| `suite_name` | `str \| None` | passthrough |
| `total` | `int` | `len(results)` |
| `passed` / `failed` / `inconclusive` / `clarification_blocked` / `errored` | `int` | counts by `outcome`; invariant `passed+failed+inconclusive+clarification_blocked+errored == total` (enforce via `model_validator`, mirroring existing validators e.g. `contracts.py:199-203`) |
| `pass_rate` | `float` (0..1) | `passed / total` (guard total==0 → 0.0). Derived; store it so the renderer/CI needn't recompute. |
| `results` | `list[TestRunResult]` | in execution order |
| `generated_at_ms` | `int \| None` | injected clock (G-L2-6); nullable so tests can omit |

### 1.4 Enum `SuiteCaseOutcome`

`PASSED / FAILED / INCONCLUSIVE / CLARIFICATION_BLOCKED / ERROR` (str Enum, matching the `TaskIntakeStatus` style `models.py:12-15`).
- `PASSED` — session reached `COMPLETED` with `last_verdict.status == VERIFIED_SUCCESS`.
- `FAILED` — a genuine regression: session `FAILED`, or verdict `VERIFIED_FAILED`.
- `INCONCLUSIVE` — couldn't determine / not a clean pass or fail: verdict `VERIFIED_UNKNOWN` or `BLOCKED`, or session `HANDED_OFF` / `AWAITING_APPROVAL` (unrunnable in a non-interactive batch). Distinct from FAILED so a regression report separates "real regression" from "flaky / blocked / needs-human".
- `CLARIFICATION_BLOCKED` — intake returned non-READY; the case never ran.
- `ERROR` — an exception was raised anywhere in the case's pipeline, or the terminal status is unmodeled (catch-all).

### 1.5 run_id provenance & determinism

`run_id` is generated by an **injected `run_id_factory: Callable[[], str]`** on `TestSuiteRunner.__init__` (default builds `f"suite-run:{uuid4().hex}"` via a new `build_suite_run_id()` in `common/ids.py` following `ids.py:8-13`). Tests inject a deterministic factory. Same pattern for `generated_at_ms` via an injected `clock: Callable[[], int]` defaulting to wall-clock ms (mirroring `memory/store.py: build_memory_timestamp_ms`). `run_id` is generated **once per `run(suite)` call** and stamped onto every `TestRunResult` — never per-case, so all rows share one run identity.

---

## 2. `TestSuiteRunner`

New module `intake/suite_runner.py`. Constructor takes the collaborators (all injectable for tests):

```
TestSuiteRunner(intake_service: TaskIntakeService,
                runtime: TaskGraphRuntime,          # SEE shared-state analysis §2.2
                *, run_id_factory=..., clock=...)
```

`run(self, suite: TestSuite) -> TestSuiteReport` loop, per case:

1. `run_id = self._run_id_factory()` (once, before loop).
2. For each `SuiteCaseInput` in `suite.cases`, wrapped in `try/except Exception as exc`:
   a. `result = intake_service.submit_test_case(case.text, platform_context=case.platform_context, confirmed=case.confirmed, session_id=None)` — **pass `session_id=None`** so each case gets a fresh `build_task_session_id()` (`session_support.py:85`) → distinct LangGraph `thread_id` (`runtime.py:121`). See §2.2.
   b. If `result.status != READY` (NEEDS_CLARIFICATION / REJECTED, `models.py:12-15`) → `TestRunResult(outcome=CLARIFICATION_BLOCKED, verdict=None, session_id=result.session.session_id if result.session else None, summary=first(clarification_questions or issues), trace_refs=result.trace_refs)`. **Do not run.**
   c. Else `result.session` is a READY session (`service.py:115-119`). `ran = runtime.run(result.session)` (`runtime.py:82-90`).
   d. Map `(ran.status, ran.last_verdict)` → outcome (§2.1).
3. Aggregate counts + pass_rate → `TestSuiteReport`.

Any exception in a/c/d → `TestRunResult(outcome=ERROR, verdict=None, summary=str(exc), session_id=<if known>, trace_refs=<if known>)`; loop continues (G-L2-2).

### 2.1 Outcome-mapping rules (exact, status-FIRST, exhaustive)

**Keyed on `session.status` FIRST (R1 fix), with `last_verdict.status` only as a refinement of the COMPLETED case.** Rationale: `last_verdict` is a single mutable field (`session.py:42`) that `_complete_step_without_verification` does NOT update when it transitions a run to FAILED (`session_support.py:147-156`) — so a stale `VERIFIED_SUCCESS` must never by itself decide PASSED. Evaluate in this order:

| # | condition | outcome |
|---|---|---|
| 1 | intake `result.status != READY` (case never ran) | `CLARIFICATION_BLOCKED` |
| 2 | exception raised anywhere in the case pipeline (incl. `GraphRecursionError`) | `ERROR` |
| 3 | `session.status == COMPLETED` and `last_verdict is not None and last_verdict.status == VERIFIED_SUCCESS` | `PASSED` |
| 4 | `session.status == COMPLETED` but verdict missing/not success | `INCONCLUSIVE` (completed without a success verdict — anomalous; keep out of PASSED) |
| 5 | `session.status == FAILED` and `last_verdict.status == VERIFIED_FAILED` | `FAILED` |
| 6 | `session.status == FAILED` (verdict None/stale/other) | `FAILED` |
| 7 | `session.status == AWAITING_APPROVAL` | `INCONCLUSIVE` (decision #1) |
| 8 | `session.status == HANDED_OFF` | `INCONCLUSIVE` |
| 9 | `last_verdict.status in {VERIFIED_UNKNOWN, BLOCKED}` (any non-terminal-looking status carrying such a verdict) | `INCONCLUSIVE` |
| 10 | **catch-all** — any `(status, verdict)` not matched above | `ERROR` with summary `f"unmapped terminal state: status={session.status}, verdict={verdict and verdict.status}"` |

`runtime.run` only returns on the terminal set `{COMPLETED, FAILED, AWAITING_APPROVAL, HANDED_OFF}` (`runtime.py:83-89`), so rows 3-8 cover every state `run` can hand back; rows 1/2/9/10 cover intake-blocked, exceptions, verdict-carrying edge cases, and the safety net. There is NO silent fall-through (R2 fix). Success is proven ONLY by row 3 (`COMPLETED` + `VERIFIED_SUCCESS`, `contracts.py:47`), aligned with verified completion (`session_support.py:135-145`).

No hang risk: LangGraph bounds each run via the default recursion limit + the per-step `max_iterations` guard (`nodes.py:121`); non-convergence raises `GraphRecursionError`, caught by row 2.

### 2.2 Shared-state analysis

**Verdict: one `TaskGraphRuntime` CAN be reused across cases, provided each case gets a distinct `session_id`.** Evidence:

- The graph is `thread_id`-scoped to `session.session_id` (`runtime.py:121`). Distinct session_ids ⇒ distinct checkpointer threads ⇒ no LangGraph state bleed. Passing `session_id=None` yields a fresh `uuid4`-based id per case (`session_support.py:85`, `ids.py:12-13`). **Hazard IF the caller reused one explicit `session_id`** — the runner MUST pass `session_id=None`. Documented as a runner invariant.
- Pipeline components (`TestCaseParser` `interpreter.py:14-23`, `AssertionSynthesizer` `synthesizer.py:38-49`, validator, assembler) hold only immutable config — no per-call mutable state. Safe to reuse.
- **Cross-case coupling — memory writeback.** `TaskMemoryRuntime` accumulates `self._writeback_results` across sessions (`memory/runtime.py:53,110,117,196`) and persists into the shared `TaskMemoryStore` (`store.py:56-62`), so case N can influence case N+1's retrieval (`memory_support.py:29-40`). Intended cross-session learning, but makes suite results **order-dependent**. Per decision #3, regression runs default to `memory_runtime=None` (`runtime.py:37`, `session_support.py:67-69` no-op when None).
- No other writeback leaks: each `TaskSession` is fresh per case (`session_support.py:84-91`).

---

## 3. `TestSuiteReportExporter`

New module `runtime/suite_report_export.py` (beside `runtime/trace_export.py`), mirroring `ExecutionTraceExporter`: `export_json(report) -> dict`, `export_markdown(report) -> str`, `dumps_json`, `write_json`, `write_markdown` (`trace_export.py:24-138`). Reuse the SAME `_redact` classmethod + `SENSITIVE_KEYS` discipline (`trace_export.py:10-21,140-152`) applied to the final payload (`trace_export.py:69`). Since `TestRunResult` embeds a `VerificationVerdict` (evidence/summaries), redaction on the dumped dict is mandatory.

**JSON:** `report.model_dump(mode="json")` piped through `_redact`.

**Markdown layout:**
```
# Test Suite Report: {suite_name or suite_id}
- Run: {run_id}
- Suite: {suite_id}
- Total: {total}  Passed: {passed}  Failed: {failed}  Blocked: {clarification_blocked}  Errored: {errored}
- Pass rate: {pass_rate:.1%}

## Summary
| case_id | outcome | verdict | summary | trace |
|---|---|---|---|---|
| checkout-01 | PASSED | verified_success | - | task-session:… |
| logout-02 | FAILED | verified_failed | Login button still present | task-session:… |
| bad-prose-03 | CLARIFICATION_BLOCKED | - | What is the expected result? | - |
| flaky-04 | ERROR | - | KeyError: … | - |
```
Per-row `verdict` = `result.verdict.status.value` or `-`; `trace` = `result.session_id` or first `trace_refs` or `-`. Follow the `ExecutionTraceExporter.export_markdown` line-building idiom (`trace_export.py:71-123`).

**R4 — redaction discipline (mandatory):** BOTH `export_json` and `export_markdown` MUST build from the SAME `_redact(report.model_dump(mode="json"))` payload. The Markdown renderer reads its row values out of that redacted dict, NOT from the raw `result.verdict`/`result.summary` objects — otherwise free-text fields (`verdict.summary`, `blocked_reason`, exception strings) bypass redaction. This mirrors `ExecutionTraceExporter.export_markdown` sourcing from `export_json` (`trace_export.py:72`). Note the residual limitation (same as the existing exporter): `_redact` is KEY-based (`trace_export.py:140-152`), so secrets embedded in free-text VALUES are not scrubbed; the summary fields the runner writes must therefore never be built from raw model/observation text containing secrets — keep them to fixed phrases + ids.

---

## 4. Public API + exports

**Standalone `TestSuiteRunner` (decision #4).** `TaskIntakeService` is a *compiler* (prose → session); it deliberately stops at `create_session` returning a not-yet-run session (`service.py:108-120`). The suite loop needs BOTH the intake service AND `runtime.run`, and produces run *results* — a concern above intake. A `TestSuiteRunner` composing `(TaskIntakeService, TaskGraphRuntime)` keeps each boundary single-purpose and L0+L1 untouched (G-L2-4).

**Exports (`intake/__init__.py`, additive to `__init__.py:1-58`):** add `TestSuite`, `SuiteCaseInput`, `TestRunResult`, `TestSuiteReport`, `SuiteCaseOutcome`, `TestSuiteRunner`. The exporter is exported from `runtime/__init__.py` beside `ExecutionTraceExporter`.

---

## 5. L3 seams (grow without reworking L2)

- **`run_id` becomes real run identity.** Today a per-invocation id; L3 promotes it to a persisted CI run id (the `run_id` shape recurs across `platform/types.py:100,126,221`). CI webhook supplies `run_id` via the injected factory (G-L2-6) — zero L2 change.
- **Per-(case × device) results.** `TestRunResult` keys on `(run_id, case_id)`. L3 adds a `device_id`/`profile` dimension → new field + a `list[TestRunResult]` per case; aggregation stays. `create_session(session_id=...)` already accepts an external id (`session_support.py:81`) so CI drives one session per (case×device) without touching intake.
- **Compatibility matrix.** `TestSuiteReport.results` is a flat correlated list — a matrix view is a projection L3's dashboard builds (G-L2-3), no L2 rework.
- **Concurrency.** The serial loop is the only thing L3 replaces with fan-out; outcome-mapping + aggregation are pure functions of `(status, verdict)` per case, concurrency-agnostic.

---

## 6. Task decomposition (rough; plan skill details later)

1. `common/ids.py`: add `build_suite_run_id()` (mirror `ids.py:8-13`).
2. `intake/suite.py`: `TestSuite`, `SuiteCaseInput`, `SuiteCaseOutcome`, `TestRunResult`, `TestSuiteReport` (+ count/pass_rate `model_validator`).
3. `intake/suite_runner.py`: `TestSuiteRunner` with injectable `run_id_factory`/`clock`; loop + outcome-mapping + try/except isolation.
4. `runtime/suite_report_export.py`: `TestSuiteReportExporter` reusing `_redact`/`SENSITIVE_KEYS`.
5. Exports: `intake/__init__.py`, `runtime/__init__.py`.
6. Tests: outcome-mapping matrix (each `TaskStatus` × `VerificationStatus` combination in the §2.1 table, incl. COMPLETED+success→PASSED, COMPLETED+no-verdict→INCONCLUSIVE, FAILED→FAILED, AWAITING_APPROVAL→INCONCLUSIVE, HANDED_OFF→INCONCLUSIVE, and an intentionally-unmapped state→ERROR catch-all); stale-verdict guard (session FAILED while `last_verdict` still VERIFIED_SUCCESS → FAILED, not PASSED — R1 regression test); failure-isolation (one ERROR case doesn't abort the batch); CLARIFICATION_BLOCKED without run; run_id determinism (injected factory); pass_rate + count-invariant math (incl. total==0); exporter JSON+Markdown with redaction AND field-masking of `session_id`/`verdict_id`/nested ids (R5 — no full-report golden); distinct-session_id invariant; order-independence with `memory_runtime=None`.

---

## 7. Resolved decisions

All five open questions are resolved in the "Finalized decisions" block above (AWAITING_APPROVAL→ERROR; SuiteCaseInput.case_id authoritative; memory_runtime=None default; standalone TestSuiteRunner; lightweight trace reference).
