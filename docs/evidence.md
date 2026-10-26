# Evidence ledger

## 2026-10-09 — P0/A3 candidate: tenant-scoped trace replay

### Scope

- Current worktree at `a0d8578a94fc0d0c7759b018c23a5d530f83a391`, with pre-existing uncommitted candidate changes; this is not a promoted baseline.
- Added `backend/scripts/render_task_trace.py`, a local, read-only static HTML renderer for an existing task. It requires both `company_id` and `task_id`, applies the tenant scope before loading records, and renders task/attempt/event/model/tool audit metadata only. It intentionally excludes task text, prompts, SQL, tool arguments/results, report body, and event-detail payloads.

### Commands and results

- `python -m pytest tests/scripts/test_render_task_trace.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` (Python 3.13 project environment): `28 passed`; the only warning is the existing Starlette `TestClient` deprecation warning.
- `ruff check scripts/render_task_trace.py tests/scripts/test_render_task_trace.py app/modules/evaluation/business.py app/modules/evaluation/business_schemas.py app/modules/evaluation/observation.py`: passed.
- `git diff --check`: passed (Git emitted existing CRLF conversion warnings for unrelated modified files).
- Against the current running local PostgreSQL stack, `render_task_trace.py --company-id 1 --task-id 115` wrote `evaluation-runs/trace-task-115-20261009.html`; task 115 is a real terminal `partial` chain with Planner, Data, Knowledge, Reviewer and persisted events.
- The same command for task 114 wrote `evaluation-runs/trace-task-114-20261009.html`; task 114 is a real terminal `failed` chain containing persisted retry transitions and model-call error categories.
- The out-of-scope control `--company-id 999 --task-id 115` failed with `task was not found in the requested company scope` and did not create an export. The integration test covers the same company-boundary behavior.

### Proven conclusions

- An operator can now replay the persisted timing and causal order of normal terminal and retry/failure task traces without exposing payload content in the artifact.
- A task cannot be exported merely by knowing its ID under a different requested company scope.

### Not proven

- This is a local trace viewer, not a complete distributed tracing or tamper-proof audit system.
- The two historical task traces do not establish business-answer correctness, a successful full evaluation run, current model availability, or recovery correctness at every failure point.
- P0 remains incomplete: the legacy runnable fixture has only 5 development and 1 heldout case; the new 23-development/7-heldout Gold still lacks task mappings, measured per-case time/cost, and a reproducible current baseline.

## 2026-10-09 — P0-2 candidate: frozen 30-case Gold contract

### Scope

- Added `backend/tests/fixtures/evaluation/business_gold_v1.json`: 30 reviewable cases derived from the fixed-seed demo business scenarios and their documented boundaries, not from a model's private rationale.
- The fixture contains 23 development and 7 heldout cases. Its primary coverage tags are Planner (4), Data/SQL (5), Knowledge/RAG (5), Reviewer/publish (4), security/scope (4), insufficient/refusal (3), and collaboration/recovery (5); every primary dimension has one heldout case.
- The evaluation contract now preserves `needs_clarification` as a terminal observation outcome and permits an intentional null business route. This fixes the prior inability to evaluate a safe pre-tool clarification/refusal decision.

### Commands and results

- `python -m pytest tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py tests/scripts/test_render_task_trace.py -q` (Python 3.13 project environment): `31 passed`; the only warning is the existing Starlette `TestClient` deprecation warning.
- `ruff check app/modules/evaluation/business_schemas.py app/modules/evaluation/observation.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py scripts/render_task_trace.py tests/scripts/test_render_task_trace.py`: passed.
- `python -m json.tool tests/fixtures/evaluation/business_gold_v1.json`: passed.
- `git diff --check`: passed (with existing unrelated CRLF conversion warnings).

### Proven conclusions

- The frozen fixture's required split and dimension distribution are mechanically checked; accidental removal, duplicate IDs, an unlabeled case, or moving a case out of its heldout coverage bucket fails the test.
- A persisted `needs_clarification` task is no longer rejected by the observation adapter merely because it did not enter Data, Knowledge, or Reviewer.

### Not proven

- The new Gold cases have not been executed against 30 fresh persisted tasks. The current task map is a placeholder and does not match this fixture; therefore no run artifact, quality rate, latency, cost, or candidate promotion exists.
- Security requests rejected before task creation still need a request-level observation adapter; they cannot honestly be represented as a fabricated persisted task.
- Document chunk IDs are runtime/index-version identifiers. The fixture records approved document paths and expects the task's frozen scope to be rechecked at execution; a stable immutable chunk-version binding remains a P1 prerequisite rather than being faked in P0.

## 2026-10-09 — P0 worktree health audit: candidate remains unpromoted

### Commands and results

- Full backend suite, run to a terminal exit in the Python 3.13 project environment: `540 passed, 6 skipped, 1 warning in 32.66s`. The warning is the existing Starlette `TestClient` deprecation warning.
- The first audit run exposed three stale assertions caused by already-present additive report/Planner schema changes: report drafts now default to schema `1.1`; API normalization adds `attachment_citations: []` to a valid stored `1.0` report; Planner normalization adds `evaluation_scope: null`. The tests now assert normalized public contracts while retaining old-version inputs as compatibility coverage. Each minimal reproduction passed before the full rerun.
- `ruff check app tests scripts`: failed with 416 findings, primarily pre-existing import ordering and rule violations across the whole candidate worktree. The focused Ruff checks for the changed evaluation and trace files pass.
- `git diff --check`: passed, with existing CRLF conversion warnings for unrelated modified files.

### Audit decision

- **P0 is not approved; do not enter P1.** The full test suite establishes regression evidence for the current dirty candidate, not a clean promoted baseline. The global lint debt, placeholder task mapping, absent request-level rejection observation, absent 30-task real run, missing measured cost, and missing current model/Worker baseline remain blocking evidence gaps.
- No full-tree auto-format was applied: it would rewrite many user-owned, already-modified files and would obscure the functional candidate changes. Any lint-remediation package must be separately baselined and audited.

## 2026-10-09 — P0 current-image startup check: services are runnable, Agent outcome unproven

### Commands and results

- `docker compose build api worker report-worker`: completed successfully from the current dirty worktree. The current Worker image includes the configured CPU Torch and sentence-transformers dependencies rather than reusing the prior two-week-old image.
- `docker compose up -d api worker report-worker`: recreated only those three services; PostgreSQL, Redis, ClamAV, Beat, and the migration dependency were retained. The migration service exited successfully before the recreated services started.
- `GET /health/live`: `200 {"status":"ok","database":null}`. `GET /health/ready`: `200 {"status":"ok","database":"ok"}`.
- Current API and both Workers remained up. Worker logs show registration of `process_analysis_task`, Outbox publication/recovery tasks, and Redis connectivity. The running configuration reports `LLM_PROVIDER=deepseek` and `LLM_MODEL=deepseek-v4-flash`; no credential values were recorded.

### Proven conclusions

- The current candidate can be rebuilt and started against the existing local PostgreSQL/Redis stack, and its API readiness check reaches the database.
- The normal Worker process can start with the current dependency set and connect to the configured broker.

### Not proven

- Service readiness is not an Agent E2E result. No new authenticated conversation submission has yet traversed Conversation -> Outbox -> Worker -> terminal task on the current image, so current model availability, task latency, outcome, and cost remain unproven.
- P0 remains **not approved**. The global lint debt, 30-case task mapping/run gap, request-level rejection observation gap, and current authenticated Worker baseline still block entry to P1.

## 2026-10-09 — P0 current-image authenticated E2E: bounded failure is recorded, not promoted

### Scope

- Created a new local QA member with a one-time high-entropy API credential; the credential was used only in-process and was not written to this ledger, source, logs, or command output.
- Through the current HTTP API, that member created a company-scoped conversation using the ready data source and submitted one low-risk message. This created task `116` through `Conversation -> Outbox -> Worker`; no existing user or conversation was reused.

### Commands and results

- `POST /conversations`: `201`; `POST /conversations/94/messages`: `202`; task `116` was accepted and claimed by the current Worker.
- The Planner model call succeeded (`1249` prompt tokens, `449` completion tokens). The following semantic-review calls received HTTP 200 but supplied no usable JSON content. The task made three bounded execution attempts, then reached terminal `failed`; it did not enter Data, Knowledge, Reviewer, or publish a report.
- Before the gateway fix, the four empty semantic-review responses were conservatively retained in `model_call_records`, but misclassified as `unexpected_error/provider_unexpected_error`. Their recorded monetary value is `0.000000`; this is **not evidence of zero provider cost**, because no current provider price table or settlement integration exists.
- Added gateway regression coverage for empty JSON output and changed both DeepSeek and OpenAI gateways to record `retryable_error/provider_empty_json_response` while preserving the pre-request token estimate. The related gateway, semantic-review, execution, and evaluation tests passed (`33 passed`); focused Ruff checks passed.
- The live task exposed a separate measurement defect: it used about 37 seconds across retries but persisted `duration_ms=42` because every retry overwrote `AnalysisTask.started_at`. `claim_execution` now preserves the first successful claim timestamp and a new regression test proves a retry cannot reset it. This defines task work duration as first claim to terminal state; per-attempt timing remains in `TaskExecutionAttempt`, and queue-wait timing is still unmeasured.
- Rebuilt and restarted the current Worker after both fixes. It registered analysis and Outbox tasks and connected to Redis.

### Proven conclusions

- The current image's authenticated API, company-scoped conversation creation, transactional Outbox publication, Worker claim, Planner call, semantic-review failure, bounded retry, and terminal failure persistence all executed against real local dependencies and the configured remote model.
- Empty structured output is not converted into a successful business result, and the corrected code has a deterministic regression test for its retryable audit classification.
- Cross-retry task work duration now has a deterministic regression test instead of being silently reset on each claim.

### Not proven and audit decision

- The gateway classification and duration fixes have not yet been exercised by a second paid live task. The configured model's empty semantic-review output remains an unresolved provider/model compatibility failure, not a fixed E2E success.
- This single failed task is neither a 5-case baseline nor a 30-case evaluation. It provides no business quality, reliable latency, cost, successful publication, or model-availability claim.
- **P0 remains not approved; do not enter P1.** The 30-case task map/run, request-level rejection observation, current cost settlement, successful and failed multi-case baseline, and whole-worktree lint debt remain open.

## 2026-10-09 — P0 automatic re-audit after current-image failure fixes

### Re-audit evidence

- Full backend suite in the project Python 3.13 environment: `542 passed, 6 skipped, 1 warning in 34.29s`. The only warning is the pre-existing Starlette `TestClient` deprecation warning.
- Focused gateway, semantic-review, workflow execution, and evaluation tests: `33 passed`; focused Ruff checks for the changed files passed.
- The full `ruff check app tests scripts` still fails with `413` findings (`234` auto-fixable plus hidden unsafe fixes). This count fell from the previous `416` only because imports in the three files touched by this slice were corrected. No whole-tree auto-fix was applied to the pre-existing dirty worktree.
- `git diff --check`: passed, with existing unrelated CRLF conversion warnings.
- `render_task_trace.py --company-id 1 --task-id 116` generated `evaluation-runs/trace-task-116-20261009.html`; the renderer's two trace tests and focused Ruff check passed. It records the current-image Planner success, semantic-review failure, retry transitions, and terminal failure without rendering task text, prompt, SQL, tool payloads, report body, or event details.

### Gate decision

- **P0 is not approved; do not enter P1.** Regression tests, trace rendering, and bounded failure behavior are necessary evidence but do not satisfy P0's exit criteria.
- Blocking gaps are: a reproducible 30-case map and evaluator run with explicit real/simulated labels; request-level observations for pre-task denials; at least the required normal and failure multi-case baseline with current Worker evidence; reliable provider cost status/settlement; a resolved structured-output compatibility path or an explicitly frozen supported model configuration; and the still-failing whole-worktree lint gate.

## 2026-10-09 — P0/A3 structured-JSON compatibility candidate: one real terminal downgrade

### Scope

- The prior live task `116` showed that DeepSeek returned HTTP 200 with empty `message.content` for JSON-mode semantic review. DeepSeek documents both nullable completion content and that JSON output can occasionally be empty; it also documents an `extra_body.thinking.type` request option.
- The candidate applies that option only in `DeepSeekGateway` when the existing caller has already requested `json_mode=True`: `{"thinking": {"type": "disabled"}}`. It leaves ordinary chat calls, the configured model name, budget limits, deterministic validation, and terminal outcome rules unchanged.
- This is an unpromoted model-request candidate, not a claim that thinking is generally undesirable or that the model/provider is now supported for all business tasks.

### Commands and results

- `pytest tests/modules/runtime/test_model_gateway.py tests/modules/analysis/test_semantic_review.py tests/integration/workflow/test_tasks.py -q`: `33 passed, 1 warning`; focused Ruff for the modified gateway and test passed.
- Rebuilt and restarted only the current `worker` service with `docker compose build worker` and `docker compose up -d worker`; it registered its tasks and connected to Redis.
- A newly created local QA member with an in-process one-time API credential submitted task `117` through the current HTTP `Conversation -> Outbox -> Worker` path. No existing account, credential, or conversation was reused or recorded.
- Task `117` reached terminal `needs_clarification` in `11120 ms` on its first execution attempt. Persisted node order was Planner -> semantic review -> Data -> Reviewer -> deterministic router -> Planner -> semantic review -> terminal save. Its seven model-call rows all recorded nonzero completion tokens (`126`, `118`, `232`, `137`, `151`, `143`, `136`) and `success`; no empty JSON response or retry occurred.
- `render_task_trace.py --company-id 1 --task-id 117 --output evaluation-runs/trace-task-117-20261009.html` wrote the scoped metadata-only trace. Trace, gateway, execution, and integration regressions then passed: `42 passed, 1 warning`; focused Ruff passed.
- A full-suite invocation was started after this small candidate change, but the shell runner stopped returning its output before a terminal exit status. It is therefore not recorded as a new full-suite pass; the prior `542 passed, 6 skipped` remains evidence for the earlier worktree only.

### Proven conclusions

- On this one current-image task, the explicit JSON-mode request option allowed all observed structured nodes to return parseable content and complete their persisted stages.
- With the ready source containing insufficient business evidence, the system did not publish a fabricated report; it finished as `needs_clarification`. This is a valid safe downgrade, not a successful business-answer measurement.
- The trace contains the terminal timing and causal order without exposing request text, prompts, SQL, tool payloads, or report body.

### Not proven and automatic gate decision

- One task is not a reliability baseline. The candidate has not yet been tested across the required normal and failure cases, a retry, a report-publication path, document/RAG evidence, or a real SQL business-result path.
- Recorded model cost remains `0.000000` without provider price/settlement integration and must remain treated as unknown, not free.
- **P0 is not approved; do not enter P1.** The reproducible 30-case map/evaluator run, request-level evidence for pre-task denials, required multi-case current Worker baseline, cost status, clean whole-worktree lint gate, and a frozen supported-model decision remain open.

## 2026-10-09 — P0/A3 request-rejection observation: scoped denial without task side effects

### Scope

- Added `analysis_request_rejections`, a company-scoped RLS table whose record contains only request correlation ID, fixed operation name, 4xx status, and timestamp. It deliberately excludes request body, API credential, raw target path, target resource ID, prompt, and report content.
- The conversation authorization dependency stores the already-established current company on request state. Middleware records only a denied `POST /conversations/{id}/messages` with an authenticated company context and status 403/404/409/422. Replayed request IDs preserve the original audit row; an audit-write failure does not change the already-denied HTTP response.
- `observation_from_request_rejection` reloads the audit row under that company scope and queries `analysis_tasks` by the same request ID. It exposes `no_side_effects=passed` only when no task exists. The evaluator now has an explicit `security_rejection` case kind: it requires rejection, no side effects, expected terminal failure, budget compliance, and a passed security gate; irrelevant report/SQL/citation metrics are `null`, not false or secretly inapplicable.

### Commands and results

- Added migration `n1a2b3c4d5e6`; after explicitly rebuilding the `migrate` image, `docker compose run --rm migrate` upgraded the local database from `e8f9a0b1c2d3`, and a fresh migration check reported `n1a2b3c4d5e6 (head)` for both current and head.
- Targeted integration/evaluation suite: `43 passed, 1 warning`. The warning is the existing Starlette `TestClient` deprecation warning. Focused import and undefined-name checks passed.
- Rebuilt the API image. A new company-1 QA member made one HTTP `POST /conversations/96/messages` against a conversation owned by another company. It returned `404`; the scoped database audit row has operation `conversation_message`, status `404`, and the task count for that request ID is `0`.
- The live request-rejection adapter returned `outcome=failed`, `rejection=passed`, `side_effects=passed`, and `model_calls=0`.
- The first migration attempt used an old `migrate` image while the API image contained new code, so the table did not exist and the audit write was logged without changing the HTTP 404. Rebuilding the separate `migrate` service resolved this; only the post-migration request above is evidence of the completed path.

### Proven conclusions

- A cross-company conversation-message attempt can now be replayed by request ID as a tenant-scoped, payload-free security observation, and the evaluator can pass it only on explicit denial and zero task side effects.
- Safety counterexamples no longer fail merely because they correctly did not produce a business report; absent rejection or side-effect evidence remains `unknown` and blocks promotion.

### Not proven and automatic gate decision

- Only the cross-company denial has live proof. The other three frozen security cases, the remaining 26 task-backed Gold cases, and a full 30-case evaluator artifact are still absent.
- This does not prove all 4xx paths, authorization failures before a company context, or every possible side effect type. It specifically proves no `AnalysisTask` was created for this protected endpoint and request ID.
- **P0 remains not approved; do not enter P1.** Current blockers are the complete reproducible 30-case task/rejection mapping and evaluator run, the required multi-case normal/failure current Worker baseline, provider cost settlement state, a frozen supported-model decision, and the whole-worktree lint gate.

## 2026-10-09 — P0 automatic re-audit: current Worker partial outcome and full regression

### Commands and results

- A new company-scoped QA conversation submitted task `118` through the current HTTP API and Worker. The task reached `partial` in `9542 ms`; persisted node events show two complete Planner -> semantic review -> Data -> Reviewer cycles, then a final Planner and semantic review. All nine recorded model calls had nonempty completion tokens.
- The task's terminal error is `model_budget_exhausted`. Its frozen model budget is `max_total_tokens=12000`; persisted usage is `13087` actual tokens across nine calls. The next call was rejected, so the task stopped safely, but actual returned completion tokens can exceed the pre-call prompt-only reservation.
- Full regression was run in bounded groups in the project Python 3.13 environment: `pytest tests/modules -q` => `477 passed, 3 skipped`; `pytest tests/integration -q` => `68 passed, 3 skipped`; `pytest tests/scripts -q` => `2 passed`. Each run emitted only the existing Starlette `TestClient` deprecation warning. `git diff --check` passed, with existing CRLF conversion warnings.

### Audit decision

- The task establishes a current-image, structured-output, multi-node `partial` baseline; it does **not** establish numerical business correctness, report publication, or a successful current business result.
- The `max_total_tokens` observation is a B1 hardening gap: reservation currently knows prompt estimate but cannot pre-reserve a bounded completion allowance. It must be fixed in B1 rather than hidden by calling the current accounting a strict total-token cap.
- **P0 remains not approved; do not enter P1.** The 30-case task/rejection map and evaluator artifact, enough current normal/failure cases, cost settlement state, supported-model decision, and whole-worktree lint gate are still required.

## 2026-10-09 — P0/A2b evaluator runner: explicit simulated-unavailable 30-case baseline

### Scope and contract

- `EvaluationObservation.source` now distinguishes `persisted_task`, `request_rejection`, and `simulated`. The two persisted adapters declare their sources; the artifact records a source count instead of inferring that every observation came from a Worker.
- `run_business_evaluation.py --simulate-unavailable` is a deliberately narrow no-dependency mode. It cannot be combined with task or rejection maps, opens no database session, and creates a failed, zero-call, zero-token observation per frozen case. It never reads Gold expectations to manufacture a passing result.
- The generated report carries a warning that it does not prove an Agent, Worker, model, database, or security-rejection path. Real runs still require exact task and rejection maps for their corresponding case kinds.

### Commands and results

- Focused evaluator/adapter suite: `pytest tests/modules/evaluation/test_run_business_evaluation.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_rejection_observation.py -q` => `35 passed, 1 warning`. The warning is the existing Starlette `TestClient` deprecation warning.
- Focused import/undefined-name check for the changed evaluator files passed. `git diff --check` passed, with existing CRLF conversion warnings.
- A real local CLI invocation wrote the ignored artifact `evaluation-runs/p0-simulated-unavailable-20261009/` using the frozen 30-case Gold fixture and the checked-in simulated environment descriptor. Its `run.json` records `cases=30`, `observation_sources={"simulated": 30}`, `simulation_mode=unavailable`, `success_count=0`, `fail_count=26`, `unknown_count=4`, and `hard_gate_status=failed`.

### Automatic audit decision

- The evaluator is now runnable across all 30 frozen cases with an explicit simulated data source and honest pass/fail/unknown output. This is only the P0 evaluator-baseline technical criterion.
- It does not supply 26 real task observations, the remaining three real security denials, normal published business results, or a current model/cost baseline. The failure result is expected for an unavailable-run simulation and is not a candidate-quality score.
- **P0 is not approved; do not enter P1.** The next P0 work must obtain real mapped observations and sufficient normal/failure Worker evidence, then rerun the evaluator before another stage audit.

## 2026-10-09 — P0 current-Worker re-audit: frozen query-contract requirements and local source dependency

### Root-cause evidence and candidate

- Task `118` had nine successful model calls but exhausted its model budget after two identical `query_contract_incomplete` paths. Its persisted checkpoints show the Planner required three capabilities while the SQL candidate's self-declared query contract matched none; `data_node` classified that as repairable and the bounded router replanned twice before the next call was rejected.
- The candidate is intentionally narrow: `DataAgent` now passes the frozen Planner `intent.required_capabilities` to `SQLGenerationService`; the SQL-generation prompt says its `query_contract.required_concepts` must copy those values exactly. It does not alter the prompt's security instructions, the controlled SQL catalog, AST validation, readonly connection, semantic SQL review, result-shape validation, or the post-generation equality check. A candidate still cannot execute SQL merely because it echoed the labels.
- New tests first failed because the old generator did not receive the frozen list, then passed after the one-path change. `pytest tests/modules/analysis/test_sql_generation.py tests/modules/analysis/test_agents.py tests/modules/workflow/test_workflow.py -q` => `74 passed, 1 warning`; the warning is the existing Starlette `TestClient` deprecation warning. Focused import/undefined-name checks and `git diff --check` passed, with existing CRLF conversion warnings.

### Current-environment evidence

- Rebuilt only `worker`. A fresh HTTP -> Outbox -> Worker task `119` no longer produced `query_contract_incomplete`; it reached the scoped SQL tool. All three tool attempts failed with `business_db_execution_failed`, and the bounded router stopped after its retry budget. Direct discovery from the Worker then proved the cause: the configured source host `demo_business_acme` could not resolve because the local demo business database service was not running. The source credential was present; no credential value was inspected or recorded.
- Started the repository-declared `demo_business_acme` and `demo_seed_acme` local services. They became healthy/seeded, and Worker-side schema discovery for the same company source passed with `22` tables.
- Fresh task `120` then reached Planner -> semantic review -> Data -> Reviewer -> deterministic router and finished `partial` in `5594 ms` with five successful model calls. It did not execute SQL: the SQL semantic reviewer returned `insufficient_schema`, so the persisted result is `partial`, report status is `partial`, and the router stopped without a retry. Its metadata-only trace is `evaluation-runs/trace-task-120-20261009.html`.
- A narrower fresh task `121` safely failed in `2103 ms` after the Planner exhausted its two structured-output attempts; it did not reach Data or SQL. This is retained as current model-output failure evidence, not hidden by a fallback response.
- Trace plus relevant analysis/workflow tests: `76 passed, 1 warning`; focused Ruff import/undefined-name checks passed. The current report still has no real successful SQL-tool call, no published normal business report, and recorded provider cost remains `0.00` without settlement.

### Automatic audit decision

- The repeated contract-mismatch root cause is fixed by a bounded, source-preserving candidate and live task `119` establishes that the execution progressed to the SQL-tool boundary. The stopped local dependency was restored and independently verified by Worker schema discovery.
- The live system safely records failure and evidence insufficiency, but neither `120` nor `121` proves a correct business result; `119` occurred before the source service was restored. The candidate is therefore not a promoted quality baseline.
- **P0 remains not approved; do not enter P1.** Required evidence still includes a real scoped SQL success and publication path, enough mapped normal/failure observations to evaluate the frozen Gold cases, the other real security denials, provider cost settlement state, a supported-model decision, and the whole-worktree lint gate.

## 2026-09-19 — A2a candidate: persisted evaluation facts and retry recovery

### Scope

- Candidate worktree only; not a clean baseline and not a promoted evaluation baseline.
- Temporary local task runs used the normal authenticated conversation → Outbox → Worker path.

### Commands and results

- `pytest tests/modules/workflow/test_task_execution_service.py tests/integration/workflow/test_tasks.py::test_worker_retries_retryable_model_error tests/integration/workflow/test_tasks.py::test_worker_retries_transient_connection_error -q`
  - 9 passed.
- `ruff check app/modules/workflow/execution.py tests/modules/workflow/test_task_execution_service.py`
  - passed.
- `git diff --check`
  - passed.
- Live task `115` reached terminal `partial` through Planner, knowledge retrieval, data query and review. Its persisted `evaluation_facts` were `entities=null`, `period=null`, `result_fingerprint=null`.
- The persisted-task adapter returned `actual_entities=null`, `actual_period=null`, `actual_result_fingerprint=null`, `returned_document_paths=[]`, and `security_check_status=passed`.
- Live task `114` showed the former retry bug: after a retryable Planner failure, later Celery attempts produced no new model calls because they resumed the failed checkpoint. The candidate now records each entered workflow node and persists a typed `RecoveryDecision`: either `retry_node` (Reviewer only) or `rerun_downstream` (Planner, semantic review, SQL/Data, RAG/Knowledge). The decision names its resume node and explicitly invalidates dependent state before the graph continues. A retryable semantic-review model failure now clears the stale `analyze` plan and reaches the retryable planning-failure path; it cannot be misreported as a user clarification or continue into Data. In particular, a Data retry invalidates its facts, RAG result and Reviewer output rather than reusing RAG merely because its document scope is unchanged. It passes only bounded retry metadata (`failed_node`, stable `error_code`, `retry_number`, `recovery_mode`) to the resumed Agent; raw error text is not Agent context, business memory, citation, or report content. The recovery regression suite passed `121 passed, 1 deselected`; the deselected task-detail assertion is an unrelated attachment-citation contract mismatch.

### Proven conclusions

- Unknown facts are not converted into empty collections or a passing fingerprint.
- Empty returned citations are represented as `[]`, while unavailable facts remain `null`.
- The deterministic citation-scope check can pass independently of business-result availability.
- A retryable outer failure no longer resumes directly at a saved failure-handler node: it invokes the actual failed node again, after applying the persisted recovery decision.
- A retryable semantic-review failure now enters the same outer retry contract rather than being silently converted into `needs_clarification`.
- Reviewer is a local retry because its inputs are already verified; SQL/Data reruns RAG and Reviewer, RAG/Knowledge reruns Reviewer, and Planner reruns its entire downstream chain.
- SQL/Data, RAG/Knowledge and Reviewer retry contexts carry their corresponding stable error codes; the Router remains deterministic and is not replaced by an Agent decision.
- A process-level retry with a recorded entered node restarts that node; without any entered-node checkpoint it safely starts from frozen task inputs.

### Not proven

- No successful real Worker task has yet produced populated `entities`, `period`, and a SQL result fingerprint for the current candidate.
- The SQL-generation provider returned a retryable failure in task `115`; this does not prove SQL correctness, answer quality, or a successful business evaluation.
- No fixture Gold values were derived from these candidate task outputs.
- The recovery-decision behavior is covered by deterministic tests, not yet by a fresh real Worker/Model failure at each node followed by successful retries.

## 2026-09-21 — A2b candidate: partial-result follow-up actions

### Contract and verification

- `EvaluationCase.expected_recommendation_actions` now declares required operator-facing follow-up action text; `EvaluationObservation.actual_recommendation_actions` reads the persisted `FinalAnalysisReport.recommendations[].action`; the deterministic evaluator fails `required_recommendation_actions_present` when a required action is absent.
- This reuses the existing report contract rather than inventing a second recommendation representation: every persisted `Recommendation` already must cite at least one confirmed fact or an evidence-bound hypothesis. It permits a partial report to preserve verified data facts, state its evidence limitation, and recommend a labeled next investigation step without turning that step into a confirmed cause.
- `pytest tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q`: `27 passed`.
- `ruff check app/modules/evaluation/business_schemas.py app/modules/evaluation/business.py app/modules/evaluation/observation.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py`: passed.
- `git diff --check`: passed.

### Boundary

- Required action matching is deterministic substring matching, not an LLM semantic-quality judgment. Gold must therefore use stable, reviewable action topics; usefulness, prioritization, and wording still need human or future rubric evaluation.

## 2026-10-09 — P0 automatic re-audit: empty evaluation scope and numeric-label false positive

### Root causes and bounded fixes

- A direct current-gateway Planner response for the generic question `2025年8月订单数量是多少？` was structurally valid but used `evaluation_scope.entities=[]`. `EvaluationScope.entities` incorrectly required at least one item, so the Pydantic boundary converted a valid no-entity metric request into `planner_invalid_output`. The field is evaluation metadata, not an authorization input; it now defaults to an empty list while retaining its eight-item cap.
- Fresh task `123` proved that the Planner path then reached a successful scoped SQL call, but the final deterministic numeric guard classified the trusted query-label period `2025` and `8` as ungrounded output values. Its first Reviewer result had `schema_valid=true`, `citations_valid=true`, and only `numbers_valid=false`; the deterministic router correctly initiated one replan, after which the task safely stopped with `model_budget_exhausted`.
- The numeric guard now removes numbers only from the exact, deterministic `数据查询（<rendered evidence purpose>）` label before scanning. It still validates every rendered result value and every other answer number against SQL rows; it does not broaden SQL scope, relax AST/read-only validation, suppress report validation, or treat arbitrary answer prose as trusted.

### Commands and results

- Test-first regression: the new trusted-query-label test initially failed against the old validator, then passed after the narrow change. `pytest tests/modules/reporting/test_reviewer_validators.py tests/modules/workflow/test_workflow_router.py tests/modules/workflow/test_worker_terminal_result.py -q` => `34 passed, 1 warning`; the warning is the existing Starlette `TestClient` deprecation warning. Focused Ruff checks passed.
- Rebuilt only `worker`. Fresh authenticated HTTP -> Outbox -> Worker task `124` for the same generic metric reached `completed` in `7852 ms`; its persisted report status is `completed`. It recorded five successful model calls (Planner, semantic review, two Data calls, Reviewer) and one successful scoped `sql_query` with one returned row. No replan or budget-exhaustion terminal occurred.
- The metadata-only trace for task `124` was rendered at `backend/storage/evaluation-runs/trace-task-124-20261009.html`. Focused cross-boundary regression then passed: `122 passed, 1 warning`; focused Ruff import/undefined-name checks passed. The trace renderer was invoked in the container with `PYTHONPATH=/app`, because an absolute script invocation otherwise sets the import path to `/app/scripts` rather than the application root.

### Automatic audit decision

- This small current-Worker normal slice is approved: the generic no-entity request no longer fails at Planner metadata validation, the controlled SQL result reaches report persistence, and numeric checks continue to cover result values while excluding only deterministic query-label context.
- **P0 as a whole remains not approved; do not enter P1.** One successful task does not replace the frozen 30-case mapped evaluator run, the remaining real security denials, sufficient normal/failure baseline coverage, provider cost settlement, supported-model decision, or the existing whole-worktree lint gate.

## 2026-10-09 — P0 automatic re-audit: reproducible first-five real baseline

### Evaluation-runner completion

- The earlier interpretation that P0 required all 30 cases to have real task mappings, clean whole-worktree lint, and provider cost settlement before advancing was inconsistent with `agent_core_first_execution_plan.md`: P0 requires a runnable 30-case evaluator with explicit real/simulated provenance, plus five visible real cases and normal/failure traces. Whole-chain quality promotion and cost settlement belong to the following core work.
- `run_business_evaluation.py` now accepts a repeated `--case-id` selector. It preserves fixture order, rejects unknown or duplicate selectors, and still requires task/rejection maps to match the selected analysis/security case set exactly. Omitting the selector preserves the existing full-fixture behavior; the simulated 30-case mode remains explicit.
- The runner also records `git_revision="unavailable"` if its runtime image has no Git executable. This is an explicit missing-fingerprint state, not a fabricated revision or an otherwise successful reproducibility claim.

### Commands and results

- Test-first runner changes: `pytest tests/modules/evaluation/test_run_business_evaluation.py -q` => `9 passed, 1 warning`; focused Ruff checks and `git diff --check` passed. The warning is the existing Starlette `TestClient` deprecation warning.
- Submitted the five fixture-ordered frozen cases through fresh authenticated HTTP -> Outbox -> Worker tasks: `planner-east-route=125`, `planner-empty-region-route=126`, `planner-policy-knowledge-route=127`, `planner-heldout-clarification=128`, and `data-east-sales-comparison=129`. No task was retried or replaced during evaluation.
- Formal real artifact: `evaluation-runs/p0-first-five-real-20261009/run.json` and `report.md`. It records five `persisted_task` observations, `success_count=0`, `fail_count=5`, `unknown_count=0`, `hard_gate_status=failed`, p95 duration `15555 ms`, 21 model calls, and 31995 observed tokens. Its task map and local-compose environment descriptor are stored alongside it.
- Normal trace remains `evaluation-runs/trace-task-124-20261009.html`: a scoped SQL call and persisted completed report. Failure trace `evaluation-runs/trace-task-125-20261009.html` records the bounded hybrid failure path. Both render only audit metadata. Evaluation and trace regression: `39 passed, 1 warning`; focused Ruff passed.

### Baseline findings and automatic stage decision

- This is a failed quality baseline, not a candidate promotion: the five cases had 60% route accuracy, 40% outcome accuracy, 40% report persistence, and zero trusted business-analysis successes. The first hybrid case had RAG retrieval failure plus SQL semantic `insufficient_schema`; the data comparison case also stopped at `insufficient_schema`. Two planning cases returned `needs_clarification` rather than their frozen expected routes/outcomes.
- The runtime documents use opaque upload paths while Gold currently names logical document paths. This makes direct path-equality citation scoring fail for the present artifact; it is an evaluation resource-identity mapping gap, not evidence that citation scope was bypassed. The task's frozen document IDs were present, and no security incident was observed in this five-case run.
- **P0 measurement/trace exit is approved, but the baseline quality result is failed.** It is now valid to continue to B0 (version recording) because B0 is not a reward for quality; it supplies the missing reproducibility fields needed before B1–B7 analyze and fix these failures. Do not claim business quality, end-to-end reliability, production readiness, or successful Gold performance from P0.

## 2026-10-09 — B0 automatic audit: execution provenance recording

### Scope and contract

- Added only passive provenance fields. Model-call records now persist a system-template identifier derived from SHA-256, a SHA-256 hash over the exact system/user prompt pair, and the actual `json_mode`, timeout, temperature, and maximum-output-token request parameters. Raw prompt, response, request body, and tool parameters remain absent from the persistence schema.
- Tool-call records now persist an explicit contract identifier (`<tool-name>/v1`) for successful, failed, and denied calls. `TaskExecutionAttempt.workflow_version` remains the existing execution-version authority; no parallel task-version field or model-routing change was introduced.
- Migration `o2b3c4d5e6f7` adds nullable model provenance fields for historical rows, an empty JSON parameter default for new rows, a prompt-hash index, and a non-null tool-contract version with a legacy-safe server default. It neither rewrites historic hashes nor claims old records have complete provenance.

### Commands and results

- TDD/contract and workflow boundary regression: `pytest tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_governance_contract.py tests/modules/runtime/test_tool_runtime.py tests/modules/runtime/test_model_gateway.py tests/modules/workflow/test_task_execution_service.py tests/modules/workflow/test_workflow.py -q` => `59 passed, 1 warning`; the warning is the existing Starlette `TestClient` deprecation warning. Focused Ruff passed; `git diff --check` passed with pre-existing CRLF warnings.
- Built `migrate` and `worker`, applied the migration, and verified `alembic current` => `o2b3c4d5e6f7 (head)`. Direct schema inspection found all three model provenance columns and the tool contract column.
- Fresh authenticated HTTP -> Outbox -> Worker task `130` completed. Its five persisted model-call rows each have a `system-sha256:` template identifier, a 64-character request hash, and the recorded JSON/timeout/temperature/max-output parameters. Its successful scoped SQL call records `sql_query/v1`. No raw prompt or response was read or persisted as evidence.

### Automatic audit decision

- **B0 is approved.** A task now links actual workflow version (attempt), model identity/parameters/prompt provenance (call rows), and tool contract version (tool-call rows) without changing execution behavior.
- This does not establish replay equivalence, provider price settlement, completion-token reservation, output truncation manifests, or a clean quality baseline. Those remain B1/C1/B3 work; proceed to B1 only through the already observed budget-overrun root cause.

## 2026-10-09 — B1 sub-slice automatic audit: output-token reservation

### Scope and contract

- The shared model-call reservation now charges estimated prompt tokens plus the configured maximum completion allowance before either external gateway sends a request. On a successful response it reconciles that reservation to the provider-reported prompt and completion tokens; on a pre-response failure it keeps the full reserved allowance charged. This closes the task-118 failure mode where completion tokens could make persisted usage exceed `max_total_tokens` after an otherwise admitted call.
- The change is intentionally limited to the common budget boundary and the two external gateways. The local simulator has no configured provider output ceiling and therefore keeps its existing zero completion reservation. It does not introduce pricing settlement, retries, context trimming, or a context-selection manifest.

### Commands and results

- New boundary tests reject a call whose prompt plus reserved completion would exceed the snapshot and reconcile a smaller actual completion result. The focused cross-boundary suite `pytest tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_governance_contract.py tests/modules/runtime/test_tool_runtime.py tests/modules/runtime/test_model_gateway.py tests/modules/workflow/test_task_execution_service.py tests/modules/workflow/test_workflow.py -q` => `61 passed, 1 warning`; the warning is the existing Starlette `TestClient` deprecation warning. Source Ruff and focused test import/undefined-name checks passed; `git diff --check` passed with pre-existing CRLF conversion warnings.
- Rebuilt the Worker. Fresh authenticated HTTP -> Outbox -> Worker task `131` completed with five successful model calls. Its persisted actual usage is `6992` tokens against the frozen `12000` limit, with no budget-exhausted terminal. The five persisted calls total the same reported prompt/completion amounts represented by the task ledger.

### Automatic audit decision

- **The B1 output-reservation sub-slice is approved.** It proves bounded admission and reconciliation for the current external-model path, not provider cost settlement or quality.
- **B1 is not complete.** Context layering, full-input accounting, deterministic truncation and its persisted selection manifest still have no implementation or evidence; continue within B1 rather than advancing to B2.

## 2026-10-09 — B1 automatic audit: bounded Planner context and selection manifests

### Scope and contract

- The frozen conversation snapshot is now v2. It keeps the existing selected history payload but adds a metadata-only `context_manifest`: source message ID, original/selected character count, tokenizer-family token count, and a deterministic `selected`, `truncated`, or `omitted` decision/reason. The manifest covers message-count, character, and token limits. A partial historical message sets `history_truncated`; Planner policy explicitly forbids inferring omitted content and requires clarification when the current question depends on it.
- Planner memory now has an independent whole-record selection bound: at most eight authorized, unrevoked records and at most 1024 tokens. Oversized records are omitted rather than sliced. Worker persists both the conversation and planner-memory selection manifests in an append-only `context_selected` event. These manifests contain only identifiers, counts and decisions; they do not contain prompt text, history text or memory text.
- External gateway budget admission now estimates both system and user content plus conservative message framing before reserving the configured maximum output. Provider-reported tokens still reconcile the task ledger. This is budget accounting, not C1 provider price settlement.

### Commands and results

- Test-first context, memory and Worker changes were followed by `pytest tests/modules/conversations/test_conversation_context.py tests/integration/conversations/test_conversations.py tests/modules/memory/test_memory_service.py tests/modules/analysis/test_planning.py tests/modules/analysis/test_agents.py tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_governance_contract.py tests/modules/runtime/test_tool_runtime.py tests/modules/runtime/test_model_gateway.py tests/modules/workflow/test_task_execution_service.py tests/modules/workflow/test_workflow.py tests/integration/workflow/test_tasks.py -q` => `151 passed, 1 warning`; the warning is the existing Starlette `TestClient` deprecation warning. Modified-source/test Ruff checks passed; `planning.py` was checked with only its pre-existing `FLY002`/`ISC004` prompt-format findings ignored; `git diff --check` passed with pre-existing CRLF conversion warnings.
- Fresh HTTP -> Outbox -> Worker task `132`, with a 16,805-character historical message, completed. Its v2 snapshot reports `history_truncated=true`, selected 2,024 characters / 1,443 history tokens, and records the long message as `truncated` for `per_message_char_limit`. Its final actual token ledger is `8723/12000` and equals its five persisted model-call prompt/completion totals.
- Rebuilt API and Worker, then fresh task `133` with nine prior history messages completed at `7844/12000` tokens. Its durable `context_selected` event reports one `message_count_limit` omission among nine manifest fragments and an empty, bounded planner-memory manifest. A recursive exact-key audit of that persisted event found no `content` key; its message fragments contain only `message_id`, decision, reason, and counts.

### Automatic audit decision

- **B1 is approved for the current Planner path.** It has explicit layer boundaries (system policy, current question, frozen history, authorized Planner memory and trusted retry feedback), bounded history/memory selection, output reservation and a real persisted selection trace.
- This does not prove provider tokenizers are identical to the local selection tokenizer, does not settle provider prices, and does not yet create selection manifests for every later SQL/RAG/reviewer prompt. Those limitations remain explicit C1/B3/B5 work; they do not permit bypassing the current gateway budget or Planner truncation rule.

## 2026-10-09 — B2 automatic audit: read-only tool contracts, timeouts and live authorization

### Scope and contract

- `ToolRuntime` now requires a registered Pydantic input contract for every current tool: `rag_search`, `sql_query`, and `template_query`. Unknown parameters are normalized away before scope checks; invalid input is denied before tool execution and only parameter names are audited.
- Each newly created task freezes SQL and RAG database timeout values in `tool_policy_snapshot`. Runtime injects those server-only values after input normalization, so a model cannot choose its own timeout. SQL passes the frozen value to PostgreSQL `statement_timeout`; RAG applies the frozen value to its scoped vector-query transaction through `set_config`.
- Before every tool call Runtime checks the task initiator's current active account and approved company membership against the explicit read-tool role matrix (`owner`, `admin`, `analyst`). This intersects current authorization with the task's frozen company/document scope. Disabled members and viewers are denied before a tool receives input.
- The current registered tools are read-only: SQL uses a read-only transaction, the registered-query path executes repository SQL, and RAG only retrieves/reranks evidence. The existing deterministic graph has at most two internal retry loops; the Worker has at most three bounded retries and retains execution ownership/checkpoints. This establishes replay safety only for these read tools, not for a future write tool.

### Commands and results

- Cross-boundary regression: `pytest tests/modules/runtime/test_tool_runtime.py tests/modules/analysis/test_tools.py tests/modules/workflow/test_workflow_router.py tests/modules/workflow/test_workflow.py tests/modules/workflow/test_task_execution_service.py tests/integration/workflow/test_tasks.py -q` => `99 passed, 1 warning`. The warning is the existing Starlette `TestClient` deprecation warning. Focused Ruff checks passed with only the pre-existing broad-exception rule excluded; `git diff --check` passed with existing CRLF warnings.
- Tests prove invalid RAG input cannot execute, user-supplied SQL/RAG timeout fields are replaced by frozen values, registered-query input is normalized, a disabled member and viewer cannot invoke a tool, and new tasks persist both timeout fields.
- Rebuilt API and Worker. A first fresh task `134` completed and recorded `sql_query/v1`, but its persisted snapshot exposed that only Worker had been rebuilt; the old API image had not frozen the new fields. This failed the audit and was corrected rather than accepted.
- After rebuilding both services, fresh authenticated HTTP -> Outbox -> Worker task `135` completed in `9254 ms`. Its persisted policy contains `sql_statement_timeout_ms=10000` and `rag_database_timeout_ms=10000`; it recorded one successful `sql_query/v1` call, one returned row, and 13 ms tool duration. Temporary QA credentials were kept in process memory and were not written to source, logs, or this ledger.

### Automatic audit decision

- **B2 is approved for the current three read-only tools.** Schema admission, frozen database timeout injection, bounded retries, read-only replay boundary, scope intersection with current authorization, audit records, and a current-image task were all checked. The temporary API/Worker image mismatch was caught by the audit before approval.
- This does not prove a cancellable deadline for local embedding or reranking CPU work; a thread timeout would leave work running and was intentionally not added. It also does not authorize or make idempotent any future writing/MCP tool, prove mid-call revocation, or replace C2 fault-injection/recovery tests. Such tools require a separately approved side-effect/idempotency design and cancellation mechanism before registration.

## 2026-10-09 — B2 automatic re-audit: current document visibility

### Reopened finding and correction

- The original B2 approval was too broad: it checked the initiator's current account and company membership, but RAG's frozen document IDs could still reference a document whose `min_view_role` had been raised after task creation. Frozen task scope is an upper bound, not a continuing authorization grant.
- `ToolRuntime` now intersects a validated, frozen RAG document list with the initiator's current approved membership role and the document's current company/`min_view_role` before reserving budget or handing input to the tool. If any document is absent or no longer visible, it records a redacted denial with `tool_document_current_authorization_denied`; no tool input is delivered. Worker code sets the tenant RLS scope before it constructs Runtime, so the lookup also remains in the task company boundary.
- The regression fixture now uses the project `set_tenant_scope` helper before inserting the RLS-protected document. This corrected a test-fixture setup error caught by the re-audit; it is not a production behavior change.

### Commands and results

- `pytest tests/modules/runtime/test_tool_runtime.py -q` => `12 passed, 1 warning`. The added case freezes document `11` for an analyst task, changes that document to `min_view_role=owner`, then proves Runtime denies the RAG call, writes a denial event, and leaves the fake tool with zero received inputs. The warning is the existing Starlette `TestClient` deprecation warning.
- `pytest tests/modules/runtime/test_tool_runtime.py tests/modules/analysis/test_tools.py tests/modules/workflow/test_workflow_router.py tests/modules/workflow/test_workflow.py tests/modules/workflow/test_task_execution_service.py tests/integration/workflow/test_tasks.py -q` => `100 passed, 1 warning`. Focused Ruff passed with only the pre-existing broad-exception rule excluded; `git diff --check` passed apart from existing CRLF conversion warnings.
- Rebuilt and restarted both `api` and `worker` images after this correction. The prior fresh task `135` remains evidence for the live SQL path and frozen timeout snapshot; this re-audit did not claim it exercises the new RAG visibility branch.

### Automatic audit decision

- **B2 is re-approved for the current three read-only tools, superseding the earlier B2 decision.** The current authorization intersection now includes account, membership, role, company, frozen scope, and RAG document visibility; the newly corrected branch is verified against the real PostgreSQL/RLS test database before tool execution.
- **Remaining boundary:** there is not yet a Worker end-to-end test that queues an authorized RAG task and changes its document visibility between freeze and execution. The Runtime/PostgreSQL regression proves the security decision boundary; it does not prove every scheduling interleaving or mid-tool revocation. This remains explicit C2/fault-injection work and does not permit a write/MCP tool.

## 2026-10-09 — B3a automatic audit: versioned chunk variants and isolated retrieval profiles

### Scope and contract

- The existing paragraph-oriented representation is now explicitly named `paragraph_v1`; a distinct `sliding_window_v1` representation uses bounded overlapping character windows, so Chinese text without whitespace remains bounded. Both variants are stored concurrently under `(document_id, chunk_strategy, chunk_index)`. Existing rows migrate to the paragraph baseline; new ingestion replaces all variants atomically only after embeddings for both variants are available.
- Baseline RAG remains `paragraph_vector_rerank_v1`. The experimental profile `paragraph_sliding_vector_rerank_v1` issues independent vector candidate queries for each chunk strategy, merges duplicate text only within the same document, and records the contributing strategy metadata on each evidence reference. The model cannot select a profile or turn reranking off: profile construction is server-side. A no-rerank profile is available only to controlled comparison code.
- A dual-profile request with frozen document IDs verifies that every requested document has every required variant. A missing variant becomes a safe retrieval failure rather than silently degrading into paragraph-only retrieval. `rag_search` is recorded as contract `v2`; SQL and template tool contracts are unchanged.
- Migration `p3a4b5c6d7e8` adds the variant key and index. Its rollback intentionally removes the candidate `sliding_window_v1` rows before restoring the old one-chunk-index invariant, preserving `paragraph_v1`; this is an explicit candidate-index rollback, not lossless dual-index retention.

### Commands and results

- Focused contract suite: `pytest tests/modules/documents/test_document_chunk_metadata.py tests/modules/documents/test_document_ingestion_service.py tests/modules/knowledge/test_retrieval_variants.py tests/modules/analysis/test_tools.py tests/integration/documents/test_document_tasks.py::test_document_worker_persists_mocked_ingestion_output -q` => `24 passed, 1 warning`, then the version-recording boundary suite => `36 passed, 1 warning`.
- Cross-boundary final suite: `pytest tests/modules/documents tests/integration/documents tests/modules/knowledge/test_retrieval_variants.py tests/modules/analysis/test_tools.py tests/modules/analysis/test_agents.py tests/modules/runtime/test_tool_runtime.py tests/modules/workflow/test_workflow.py tests/modules/workflow/test_workflow_router.py tests/integration/workflow/test_tasks.py -q` => `158 passed, 1 warning`; focused Ruff passed (the pre-existing `SIM103` in `rag/engine.py` was checked with that rule excluded); `git diff --check` found no whitespace error, only existing CRLF conversion warnings.
- The new single-case test uses the real PostgreSQL/pgvector test database and a fixed query vector: paragraph-only retrieval returns its paragraph candidate; dual retrieval runs both candidate queries and selects the stronger sliding candidate. A second case deletes the sliding row and proves the dual request fails closed. The real local embedding/pgvector document Worker integration also now proves that one file produces both indexed variants while the unchanged default retrieval path reads only `paragraph_v1`.
- Rebuilt and restarted API/Worker; the local runtime database reports migration head `p3a4b5c6d7e8`. In the isolated test database, actual Alembic `p3a4b5c6d7e8 -> o2b3c4d5e6f7 -> p3a4b5c6d7e8` completed successfully.

### Automatic audit decision

- **B3a is approved as an experimental retrieval foundation.** Two representations can coexist, dual candidate routes and a server-side rerank switch are testable, missing candidate indexes fail closed, version provenance reflects the RAG contract change, and the candidate index has a verified rollback path.
- **B3b is not complete and no quality improvement is claimed.** The single-case comparison proves plumbing and isolation only. There is no three-group 30-case development/heldout comparison, Recall@k/citation/refusal/latency/cost table, human relevance calibration, or candidate promotion. The live workflow still uses the paragraph baseline profile.

## 2026-10-10 — B3b automatic audit: three-profile retrieval comparison

### Frozen comparison contract

- The corpus is `docs/business_knowledge_base/manifest.json` (153 source documents). The comparison set is the first 30 development documents under the pre-existing stable SHA-256 source-identity split; each profile sees exactly the same document scope, question, embedding provider, candidate Top-10, and final Top-3 cutoff.
- The three profiles are: `paragraph_vector_rerank_v1` (current baseline), `paragraph_vector_no_rerank_v1` (isolates rerank contribution), and `paragraph_sliding_vector_rerank_v1` (isolates the second chunk representation/candidate route). The candidate profile does not run in the live workflow.
- The artifact records Recall@3, MRR@3, returned-candidate scope rate, retrieval sufficiency non-refusal rate, elapsed time, and cost state. Returned-candidate scope is not final-answer citation correctness; no Answer model runs in this evaluation. Local model cost remains `unknown`, not zero, until C1 settlement.

### Commands and results

- Fixed a root-cause path bug in the existing slow evaluation: its `WORKSPACE_ROOT` selected `backend/`, while the corpus lives at project-root `docs/`. The reproducible failure occurred before embedding; a direct path check confirmed the manifest exists and contains 153 artifacts. The minimal correction uses `Path(__file__).resolve().parents[4]`.
- Real command: `RUN_FULL_CORPUS_RAG_EVAL=1 RUN_B3B_RETRIEVAL_COMPARISON=1 FULL_CORPUS_TOP_K=10 pytest tests/modules/evaluation/test_full_corpus_retrieval_evaluation.py -q -s` => `1 passed, 1 warning` in `216.49s`. Its complete output is retained at `backend/storage/evaluation-runs/b3b-retrieval-20261010/pytest-output-rerun.log`; structured values are in `run.json` (SHA-256 prefix `5F520A7D5681726`).
- The full-corpus paragraph vector baseline is already weak: 153 cases, Recall@10 `0.5033`, MRR@10 `0.2362`; development is `0.4797/0.2222`, heldout is `0.6000/0.2933`. This is measurement evidence, not a release-quality result.

| Profile | Recall@3 | MRR@3 | Non-refusal | Duration | Decision |
|---|---:|---:|---:|---:|---|
| paragraph + rerank | 0.4667 | 0.4333 | 0.8333 | 99.022s | retain baseline |
| paragraph, no rerank | 0.1667 | 0.1167 | 0.8333 | 1.194s | no quality substitute |
| paragraph + sliding + rerank | 0.2000 | 0.1556 | 0.7667 | 87.632s | reject candidate |

- Candidate evidence scope rate is `1.0` for every profile: returned evidence stayed within the frozen document set. This does not prove claim-to-citation support. Focused evaluator/retrieval/tool regression passed `19 passed, 1 warning`; focused Ruff passed; `git diff --check` reported no whitespace error, only existing CRLF conversion warnings.

### Automatic audit decision

- **B3b is complete as a rejected candidate experiment.** The dual chunk/candidate route materially regresses Recall@3, MRR@3, non-refusal rate, and remains expensive; it is not promoted. The live workflow stays on `paragraph_vector_rerank_v1`.
- This does not establish answer correctness, final citation correctness, human relevance calibration, provider price, or a quality baseline fit for release. No heldout candidate confirmation is run because the candidate already fails on development; the previously measured heldout paragraph-vector result is retained as baseline-only evidence.

## 2026-10-10 — B4 automatic audit: bounded durable Planner memory lifecycle

### Scope and contract

- The three layers are now explicitly bounded by their existing call chain: working memory is the in-flight LangGraph state; session memory is the immutable `context_snapshot` selected when a conversation task is created; durable memory is `AnalysisMemory`, selected only for the next task's Planner. Durable memory is never passed to SQL, RAG, Reviewer, Composer, or deterministic publication validation.
- A durable memory write now requires a company-scoped task already published as `completed` or `partial`, `stage == completed`, a report whose status matches the task, and at least one validated confirmed fact. The stored payload remains facts plus limitations; it excludes hypotheses, recommendations, raw prompts, and citations. Repeated publication remains idempotent through the existing validated-report source key.
- New durable memories receive an explicit 30-day TTL. Selection already rejects expired or revoked rows; it now also inner-joins `MemorySource`, so legacy/orphan rows cannot be read as durable Planner context.
- Migration `q4b5c6d7e8f9` changes `analysis_memories.memory_source_id` from `ON DELETE SET NULL` to `ON DELETE CASCADE`. The ORM relationship uses passive deletion so direct source deletion reaches the database cascade rather than nulling the child first. Deleting a source therefore removes its linked memory instead of silently preserving an untraceable fact.
- The with/without-memory control keeps question, fake model output, and Planner decision fixed. The baseline prompt contains an empty memory list; the candidate contains the source-linked fact and the existing instruction that it is not a current-task fact, citation, or user instruction. This proves injection and boundary wording, not answer-quality improvement.

### Commands and results

- Pre-change relevant baseline: `pytest tests/modules/memory/test_memory_service.py tests/modules/analysis/test_planning.py tests/modules/conversations/test_conversation_context.py -q` => `20 passed, 1 warning`.
- New B4 behavior regression: `pytest tests/modules/memory/test_memory_service.py tests/modules/analysis/test_planning.py -q` => `17 passed, 1 warning`. It proves the write gate rejects an unpublished or factless report, new memory has a finite TTL, expired memory is not selected, direct source deletion removes memory, current membership loss prevents selection, and the Planner prompt's only controlled difference is the durable-memory payload.
- Cross-boundary regression: `pytest tests/modules/memory/test_memory_service.py tests/modules/analysis/test_planning.py tests/modules/conversations/test_conversation_context.py tests/modules/workflow/test_workflow.py tests/modules/workflow/test_worker_terminal_result.py tests/modules/reviews/test_review_service.py tests/integration/workflow/test_tasks.py -q` => `85 passed, 1 warning`. Broad B1–B4 regression => `196 passed, 1 warning`. The sole warning is the existing Starlette `TestClient` deprecation warning.
- Built and ran the migration container. `alembic current` in that container reports `q4b5c6d7e8f9 (head)`. API and Worker were rebuilt/restarted; logs show FastAPI startup complete and Celery's analysis worker registered. Focused Ruff checks for memory, migration and Planner test imports passed; `git diff --check` found no whitespace error, only existing CRLF conversion warnings.

### Automatic audit decision

- **B4 is approved for the current single-node Planner-memory path.** The write gate, bounded selection, TTL read exclusion, source-deletion propagation, authorization re-check and deterministic input-control comparison are executable and recorded. No memory value is promoted into a business answer or allowed to bypass current-task evidence validation.
- This does not prove that 30 days is the correct business retention policy, provide a user-facing memory deletion API, physically purge rows merely because TTL elapsed, revalidate every fact against mutable business data, or demonstrate a real-model answer-quality gain from memory. Expiry is enforced at read time; physical retention and retention policy belong to later governance/compliance work. Proceed to B5 without treating B4 as a production-retention or quality result.

## 2026-10-10 — B5 pre-implementation audit: metric semantics are not available

### Verified gap

- The current `QueryContract` records required concepts, expected result columns, result kind, and empty-result policy. `assess_query_result` verifies returned column names and row shape. It does **not** contain a metric-definition reference, time period/timezone, units/currency, source-field lineage, rounding policy, or zero-denominator policy.
- `SchemaSnapshot` discovery records only PostgreSQL table names, field names/types/nullability, and single-column foreign-key joins. It does not discover business meaning. `DataEvidence` persists SQL, columns, and rows only; `build_confirmed_facts` renders those rows directly. Therefore a successfully executed query can still use the wrong date column, missing status filter, wrong currency/unit, or an untraceable calculation.
- The existing model-backed semantic reviewer may identify obvious mismatch, but it cannot become the authority for metric definition or Claim support. Treating an LLM-declared time/unit/lineage as verified would violate the deterministic-evidence boundary.

### Automatic audit decision

- **B5 is not approved and no guessed metric catalog was added.** Adding a static mapping or default currency/timezone would silently change the semantics of arbitrary tenant snapshots, while rejecting all current snapshot queries would regress the existing verified path. Either choice would be a false completion.
- To continue B5, the first supported metric needs an owner-approved, versioned definition: metric ID/name, formula and mandatory filters, source tables/columns, time column and timezone, unit/currency, allowed dimensions/granularity, rounding and zero-denominator policy. With that concrete input, the next small slice can attach a metric reference and AST-verifiable technical lineage to `QueryEvidence`, then make Claim statuses `supported`, `refuted`, `insufficient`, or `irrelevant` without asking the model to certify them.

## 2026-10-10 — B5 automatic re-audit: controlled metric semantics and Claim evidence

### Reopened scope and source facts

- The previous B5 refusal was correct for arbitrary tenant snapshots, but a narrower, reviewed source exists for the managed demonstration business database. `backend/scripts/generate_business_data.py` defines `sales_orders.total_amount` as `NUMERIC(14,2)`, `order_date` as `DATE`, and renders the currency as `¥`; `docs/business_knowledge_base/monthly/*.md` and `backend/scripts/validate_business_data.py` use `sales_orders.total_amount` and `sales_orders.order_date` for monthly sales. There is no timestamp or timezone field, so the metric is explicitly modelled as a `business_calendar_date`, not guessed as `Asia/Shanghai` or another timezone.
- Added the source-controlled registry `backend/app/modules/analysis/metric_catalog.py`. `revenue/v1` is CNY, `SUM(sales_orders.total_amount)`, uses `sales_orders.order_date`, requires `sales_orders.status = delivered`, has scale 2 and a stated zero-denominator policy. `ticket_count/v1` is a second bounded count metric. This registry does not infer meaning from a discovered tenant schema.

### Candidate contract and deterministic gates

- `QueryContract` now carries `metric_definition_ref`, `time_scope_column`, and an optional bounded `numeric_assertion`. SQL generation exposes only registry definitions whose technical columns exist in the current snapshot, and requires a metric reference and business-date column for metric questions.
- `assess_metric_query` accepts one PostgreSQL `SELECT` only and deterministically checks the registered aggregate, all technical source columns, the metric time column, and mandatory equality filters. It reports `supported`, `insufficient`, or `irrelevant`; a missing `delivered` filter now reports the required business filter rather than a misleading generic lineage error.
- `DataAgent` runs the metric gate after the pre-existing planning and semantic-review boundaries but before SQL execution. Its normal workflow default enables semantic review. A replay carrying a registered metric contract rechecks that contract before invoking the SQL tool. The execution evidence persists metric ID, unit, time semantics, and resolved lineage columns.
- A bounded numeric assertion is deterministically classified as `supported`, `refuted`, `insufficient`, or `irrelevant`. Refuted/irrelevant assertions remain auditable evidence but are filtered from `ConfirmedFact`; Reviewer returns an explicit partial result rather than silently rendering the number as a confirmed fact.

### Verification

- Targeted B5 and reporting tests: `python -m pytest tests/modules/analysis/test_metric_validation.py tests/modules/analysis/test_claim_validation.py tests/modules/analysis/test_fact_builder.py tests/modules/analysis/test_agents.py tests/modules/analysis/test_sql_generation.py tests/modules/reporting/test_report_composer.py -q` => `64 passed, 1 warning`. The counterexamples cover a missing mandatory filter, unknown metric, multiple statements, all four Claim states, no promotion of a refuted Claim, and replay rejection before SQL execution.
- Focused static check for the B5 analysis/reporting modules and tests: `python -m ruff check ...` => `All checks passed!`.
- Cross-boundary non-regression: `python -m pytest tests/modules/memory tests/modules/analysis tests/modules/conversations tests/modules/reporting tests/modules/reviews tests/modules/workflow tests/integration/conversations tests/integration/reviews tests/integration/workflow -q` => `280 passed, 5 skipped, 1 warning`. The warning is the pre-existing Starlette `TestClient` deprecation warning.
- `git diff --check` produced no whitespace error; it still reports the existing worktree-wide LF-to-CRLF conversion warnings.
- `docker compose up -d --build api worker` rebuilt the affected runtime images. `docker compose ps` shows API and Worker running; their fresh logs show FastAPI startup complete, Worker connected to Redis, and the analysis task registered.

### Automatic audit decision

- **B5 is approved for the managed demonstration business source.** An SQL statement being executable is no longer sufficient to create a business fact: it must name a registered metric, satisfy its required business filter/time column/aggregate/technical lineage, and any explicit numeric assertion is independently classified before publication.
- This is not a claim that arbitrary company snapshots now have business semantics, that registered CNY metrics apply to every tenant, that actual model calls consistently choose the right metric, or that a real provider-backed task has completed this new B5 path. DATE-based business time intentionally has no timezone conversion. The registry currently covers two demo metrics, and rounding/zero-denominator policy is declared but not yet an expression-level SQL or cross-period calculation validator. Those are explicit later metric/evaluation work, not evidence of full production SQL correctness.

## 2026-10-10 — B6a automatic audit: execution completion is distinct from report publication

### Verified gap and mapping

- `AnalysisTask.status` already distinguished `awaiting_review`, but no stable result field explained whether a report was published, a draft was held, a partial report was shown, or a completed task was only a direct response. Therefore `completed` alone could be misread as “formal report published.”
- Added `backend/app/modules/workflow/publication.py` as the single pure mapping from terminal workflow facts to task status, attempt status, report location, and `result_data.publication`. The explicit outcomes are `published`, `published_partial`, `awaiting_human_review`, `not_published`, and `not_applicable`.
- `_save_workflow_result` now persists that record before final task persistence. A direct scope-exit reply remains task `completed` but has `publication.decision=not_applicable`; a completed validated report is `published`; a causal report is held in `report_draft` with `awaiting_human_review`; a partial result without report is not falsely called published.
- Approval now records an approved-pending-publish state, the fenced publish worker changes it to `published`, and rejection records `not_published` while retaining the draft and audit decision. The existing task/execution ownership condition remains the write boundary.

### Verification and decision

- Mapping and worker/review tests: `python -m pytest tests/modules/workflow/test_publication.py tests/modules/workflow/test_worker_terminal_result.py tests/modules/reviews/test_review_service.py -q` => `18 passed, 1 warning`.
- Cross-boundary workflow/review regression: `python -m pytest tests/modules/workflow tests/modules/reviews tests/integration/workflow -q` => `94 passed, 3 skipped, 1 warning`. The warning is the existing Starlette `TestClient` deprecation warning.
- Focused Ruff check for the mapping, worker, review service, and tests => `All checks passed!`.
- **B6a is approved.** Task execution completion and report publication now have distinct, persisted semantics. This does not yet prove every legal/illegal database state transition; B6b will make those transitions table-driven and exercise invalid edges.

## 2026-10-10 — B6b automatic audit: task-status transition table

- Added `backend/app/modules/workflow/task_state.py` as the shared legal-edge table. It permits queue/retry claiming, running-to-terminal/retry/review transitions, and only review-to-queue or review-to-partial transitions; all terminal states have no outgoing edge.
- Worker finalization/retry, human-review approval/rejection, and both task-cancellation paths call the same guard before writing status. This closes the earlier bypass where a direct review or cancellation write could avoid the Worker-only check.
- State-table tests cover legal claim/retry/review edges and illegal completed-to-running, review-to-completed, partial-to-queue, clarification-to-completed, and unknown-state edges. Existing execution, review, conversation, and integration paths remained non-regressed.
- `python -m pytest tests/modules/workflow tests/modules/reviews tests/modules/conversations tests/integration/workflow tests/integration/conversations -q` => `128 passed, 3 skipped, 1 warning`; focused Ruff => `All checks passed!` before its mechanical import-order fix, then no remaining lint findings in the selected files.
- **B6b is approved for the current task-status model.** This is not a database-level transition constraint against arbitrary direct SQL, nor a proof of every cancellation/race recovery scenario; application writes now share the rule and the existing ownership predicates remain the concurrency boundary. B7 will address Agent decision authority, failure propagation, and total-step/budget limits.

## 2026-10-10 — B7a automatic audit: deterministic Agent authority and bounded graph

- The current graph confirms the intended authority split: Planner supplies a constrained route, Data/Knowledge supply evidence, Reviewer supplies review output only, and `smart_router_node`/`choose_next_action` deterministically own retry, replan, and stop choices. Reviewer has no publish call; publication remains in the fenced Worker path audited in B6.
- Fixed a concrete reachability defect: Router could select `retry_reviewer`, but the conditional LangGraph edge map omitted `reviewer_node`. The map now contains that edge and an executable graph test verifies it.
- The existing cross-agent retry limit remains two external retries. Added a separate `MAX_GRAPH_STEPS=20` LangGraph recursion limit, so replan/retry topology cannot exceed the total graph-step ceiling even if a future route bypasses the external-retry counter.
- `python -m pytest tests/modules/workflow/test_workflow.py tests/modules/workflow/test_workflow_router.py -q` => `43 passed, 1 warning`; focused Ruff => `All checks passed!`. Cross-boundary workflow/analysis/reporting/review integration regression => `268 passed, 5 skipped, 1 warning`.
- **B7a is approved.** This proves the current bounded graph wiring and deterministic routing policy, not that every collaboration-failure category has an explicit graph-level counterexample; B7b supplies those cases.

## 2026-10-10 — B7b automatic audit: collaboration-failure counterexamples

- Reused and ran five distinct failure contracts rather than adding duplicate test scaffolding: invalid Planner state routes to failure; Reviewer retryable failure is routed only by the deterministic Router with the same evidence; external retries stop at budget; model/tool budgets reject before a new call; retry recovery resumes from trusted checkpoints and invalidates dependent state.
- The B7a reviewer-edge repair makes the Reviewer retry case graph-reachable. The 20-step LangGraph bound remains independent of the two external retry budget, so a topology error cannot silently turn into an unbounded graph run.
- `python -m pytest tests/modules/workflow/test_workflow.py tests/modules/workflow/test_workflow_router.py tests/modules/workflow/test_task_execution_service.py tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_tool_runtime.py -q` => `74 passed, 1 warning`.
- **B7b is approved for the current controlled workflow.** The evidence is local deterministic/fake-provider coverage; it does not prove production provider behavior, performance under concurrent workloads, or all future Agent nodes. B0–B7 core implementation is now ready for its consolidated regression and runtime audit before entering C1.

## 2026-10-10 — C1 automatic audit: durable model-call settlement ledger

### Verified gap and candidate contract

- The former `reserve_model_call` incremented only task-level totals. It did not persist a call identifier before contacting a provider; DeepSeek successful calls and every provider timeout/error could therefore retain `cost=0`. That is not a valid statement that a paid call was free.
- Every governed external model request now writes one `model_call_records.model_call_id` UUID and `billing_status=reserved` before the gateway sends the request. The record includes reserved input/output tokens, an optional reserved price, provider/model/parameters, pricing-table version and key. The row is then locked and finalized as `settled` or `unknown`; a second finalizer reloads the durable row and cannot create or re-charge a settled call.
- Price selection is a frozen task-policy `model_pricing` table. Entries are indexed by provider, model and an optional exact parameter subset, with a version and price ID. A matching successful provider response with token usage is settled from that mapping. A missing/malformed price mapping, no provider usage, or any timeout/error is `unknown`; its token and any known upper-bound reservation remain charged, and task usage increments `unknown_cost_calls` rather than adding a false zero-cost settlement.
- OpenAI's former hard-coded price calculation was removed. New tasks snapshot `MODEL_PRICE_TABLE_VERSION` and JSON `MODEL_PRICE_TABLE` at creation, so later environment changes cannot reinterpret an existing task. The sample configuration deliberately remains `unconfigured`/empty; it does not invent current provider prices.
- Current RAG uses local `paraphrase-multilingual-MiniLM-L12-v2` embedding and the configured local cross-encoder reranker, not a paid embedding/reranking API. Both now create pre-execution ledger rows with `charge_kind=local_resource`, input/candidate resource counters and elapsed time; they settle with a zero *monetary* value only because their resource basis is explicitly local, not because an external price is unknown.

### Verification

- New runtime and real PostgreSQL integration contracts: `python -m pytest tests/modules/runtime/test_model_settlement_integration.py tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_gateway.py tests/modules/runtime/test_model_governance_contract.py -q` => `22 passed, 1 warning`. They prove pre-request UUID/reserved persistence, provider/model/parameter price selection across two provider entries, exact settlement, timeout `unknown` with retained reservation, same-call duplicate settlement, and local rerank resource records. The warning is the pre-existing Starlette `TestClient` deprecation warning.
- Cross-boundary compatibility: `python -m pytest tests/modules/evaluation/test_observation.py tests/modules/observability/test_observability_service.py tests/integration/conversations/test_conversations.py tests/integration/workflow/test_tasks.py -q` => `38 passed, 1 warning`. This caught and then verified the ORM UUID default needed by historical/evaluation call records.
- Consolidated current-core regression: `python -m pytest tests/modules/evaluation tests/modules/runtime tests/modules/workflow tests/modules/analysis tests/modules/reporting tests/modules/reviews tests/modules/memory tests/modules/conversations tests/integration/workflow tests/integration/reviews tests/integration/conversations -q` => `378 passed, 6 skipped, 1 warning`.
- Focused changed-source `ruff --select E,F` => `All checks passed!`. `git diff --check` reports no whitespace error, only the pre-existing worktree-wide LF-to-CRLF conversion warnings.
- The owner-role `migrate` container applied `r5c6d7e8f9a0`; `alembic current` reports `r5c6d7e8f9a0 (head)`. Direct schema inspection confirms non-null `model_call_id` and `billing_status`, plus `reserved_cost`, `resource_usage`, and `settled_at`. API and Worker were rebuilt from the final source; API startup completed and Worker registered `process_analysis_task` and connected to Redis.

### Automatic audit decision

- **C1 is approved for the current call-ledger mechanics.** The system has a durable pre-call identifier, explicit `reserved`/`settled`/`unknown` states, parameter-aware frozen price lookup, idempotent finalization, and explicit local embedding/rerank resource accounting. The timeout path is no longer represented as a free call.
- This is not a claim that the current live DeepSeek environment has a verified dollar price: its active table is intentionally unconfigured, so a fresh external call remains `unknown` until an owner supplies and versions an applicable price entry. There is no paid embedding/reranker provider configured in the current source, and provider invoice reconciliation or process-kill/late-response fault injection remains C2 work. No actual-provider cost amount, invoice match, or full paid-reranker path has been asserted.

## 2026-10-10 — C2 automatic audit: injected dependency faults and safe degradation

### Confirmed fault boundaries

- The application uses cloud-model gateways with SDK retries disabled (`max_retries=0`), so tests mock the client rather than claim a real provider outage. Timeout, 429, connection loss, empty JSON and malformed response are explicit retryable outcomes; invalid authentication remains permanent. A malformed provider object now has a stable `MalformedModelResponseError` and `provider_malformed_response` audit code instead of escaping as an arbitrary SDK/object error.
- `ToolRuntime` already centralizes policy/scope/budget checks and tool audit rows. It now also rejects a tool that returns anything other than `ToolOutput`: both an in-process exception and a malformed return become the redacted `tool_runtime_unexpected_error`, a `tool_failed` event, and a failed `ToolCallRecord`; raw exception text and input content are not persisted.
- The current embedding/reranker implementation is in-process, not a separately killable child process. It is therefore tested by exception/contract injection at the runtime boundary rather than pretending that a thread can safely terminate model CPU work. SQL and RAG continue to receive frozen database statement-timeout policies.

### Ten injected cases and verification

1. Mocked cloud timeout -> retryable model failure.
2. Mocked cloud 429 -> retryable model failure.
3. Mocked cloud connection failure -> retryable model failure.
4. Mocked empty JSON -> retryable, audited provider-output failure.
5. Mocked malformed provider response -> retryable, stable malformed-response audit code.
6. Mocked invalid provider authentication -> permanent model failure.
7. In-process tool `TimeoutError` -> redacted tool failure, no raw input leak.
8. In-process tool malformed return -> the same controlled tool failure.
9. Injected transient workflow `ConnectionError` -> bounded Worker retry path.
10. Injected retryable model error -> bounded Worker retry path; existing unexpected-terminal and budget-exhaustion contracts verify it cannot become a false completed report.

- Focused injection/regression: `python -m pytest tests/modules/runtime/test_model_gateway.py tests/modules/runtime/test_tool_runtime.py tests/integration/workflow/test_tasks.py -q` => `46 passed, 1 warning`; the Starlette `TestClient` warning is pre-existing. The wider workflow/router set after malformed-response handling passed `87 passed, 1 warning`.
- Isolated database exercise: started a new no-volume container named `agent-c2-isolated-postgres`; `pg_isready` accepted connections, it was stopped (status `exited`), restarted and accepted connections again, then stopped and removed. It never joined the Compose network and did not touch the Compose business database or its data. The application's database-failure behavior remains covered by injected Worker connection-error tests, not misrepresented as a real business-database outage.
- Focused changed-source `ruff --select E,F` => `All checks passed!`. Consolidated current-core regression => `383 passed, 6 skipped, 1 warning`. API and Worker were rebuilt from the final source; API startup completed and Worker processed normal outbox/recovery ticks successfully after reconnecting to Redis.

### Automatic audit decision

- **C2 is approved for the current cloud-gateway and in-process-tool boundaries.** The tested faults are classified, bounded and persisted as failures/retries; malformed model/tool output cannot become a successful result; no test stopped the business database.
- This does not prove real provider availability/error semantics, hard cancellation of local embedding/reranking CPU work, or a kill/restart race between a paid provider response and settlement. Those remain explicit operating limits and later recovery/availability work; no successful business report is inferred from any injected failure.

## 2026-10-10 — C3 automatic audit: frozen workflow release and retry-only rollback

### Release and rollback contract

- New tasks freeze `workflow_policy_snapshot` as `{version, rollback_version}` when the repository creates them. The current configured release is `v1`; `v2-candidate` is an explicitly supported candidate reference. An execution attempt records the effective version when it is atomically claimed, so a later rollback cannot relabel its history.
- `rollback_task_workflow_version` takes a row lock and accepts only an existing `queued` or `retrying` task with an auditable prior attempt. It keeps the original frozen snapshot immutable, writes a `workflow_version_override` solely for the next claim, and appends `workflow_version_rolled_back` to the prior attempt with its source/target versions. A running task, a task with no prior attempt, and an unknown target are rejected.
- The rollback deliberately does **not** delete, refund, or rewrite a prior attempt's checkpoints, model-call ledger rows, tool-call rows, workflow events, reports, or any provider/tool side effect. An already-issued external request, an external write, an email, or a published report remains irreversible unless its own domain-specific compensating action exists; C3 supplies no such compensator. This project currently permits only the controlled read-only tool set, but that boundary must remain true before treating release rollback as safe for future write tools.

### Verification

- Same-task rollback contract: `python -m pytest tests/modules/workflow/test_workflow_versioning.py tests/modules/workflow/test_task_execution_service.py tests/integration/workflow/test_tasks.py -q` => `34 passed, 1 warning`. The new case freezes `v2-candidate`, claims its candidate attempt, persists a model ledger entry, places that same task into retrying after a simulated candidate regression, rolls back to `v1`, and proves the replacement claim uses `v1` while the candidate attempt and its model ledger entry remain unchanged. The Starlette `TestClient` warning is pre-existing.
- Changed-source `ruff --select E,F` => `All checks passed!`. `docker compose up --build migrate` upgraded `r5c6d7e8f9a0 -> s6d7e8f9a0b1`; after API/Worker rebuild, `docker compose exec -T api alembic current` => `s6d7e8f9a0b1 (head)`. Owner-role schema inspection confirmed non-null JSONB `workflow_policy_snapshot` with the `v1` default and nullable `workflow_version_override`. API startup completed; Worker connected to Redis and completed normal outbox/recovery ticks.
- Consolidated current-core regression: `python -m pytest tests/modules/evaluation tests/modules/runtime tests/modules/workflow tests/modules/analysis tests/modules/reporting tests/modules/reviews tests/modules/memory tests/modules/conversations tests/integration/workflow tests/integration/reviews tests/integration/conversations -q` => `385 passed, 6 skipped, 1 warning`. `git diff --check` found no whitespace error, only existing worktree-wide LF-to-CRLF conversion warnings.

### Automatic audit decision

- **C3 is approved for frozen release provenance and retry-only rollback routing.** A bad candidate can be removed from the next attempt of the same retrying task without erasing the failed attempt or its ledger/audit facts, and an in-flight attempt cannot be retargeted.
- **Scope limit:** `v2-candidate` is currently a release/provenance selector, not a separately implemented candidate graph whose behavioral differences have been evaluated. The test simulates its failure by a controlled retry transition; it does not prove a real cloud request, external tool side effect, report publication, or full graph execution can be reversed. No external side effect is claimed reversible, and no candidate is promoted.

## 2026-10-10 — D1 automatic audit: attachment consumption boundary (not approved)

### Reopened execution gap and narrow correction

- Source tracing found that `build_task_attachment_context` had no production caller. Conversation creation froze only `ready`, owner-scoped attachment-version IDs, but the Worker neither read verified parsed output nor supplied it to Planner. Therefore an attachment previously reached a status/binding boundary only; it was not yet consumed at execution.
- The Worker now builds the task-scoped attachment context before model execution, passes only its runtime `planner_payload` into Planner, and persists only its metadata-only `selection_manifest` in `context_selected`. Runtime attachment text is excluded from the graph checkpoint allow-list. Planner and repair prompts explicitly classify attachment text as untrusted: it cannot alter policy/tool scope and is not verified fact, citation, or final-answer evidence.
- A first regression found that the new code eagerly constructed S3 storage for tasks with no frozen attachment. A second reproduction confirmed that an otherwise valid no-attachment task then failed when S3 configuration was absent. The corrected path constructs storage only when a frozen attachment exists; empty attachment scope remains storage-independent. A new integration fixture also had to call `set_tenant_scope` before inserting the RLS-protected artifact; that was a test setup correction, not a product behavior change.

### Verification to date

- Focused runtime/context suite: `python -m pytest tests/integration/workflow/test_tasks.py::test_worker_passes_frozen_attachment_only_at_runtime tests/integration/workflow/test_tasks.py::test_worker_preserves_an_explicitly_empty_document_scope tests/modules/analysis/test_planning.py tests/modules/workflow/test_workflow.py tests/modules/input_artifacts/test_attachment_context.py tests/modules/input_artifacts/test_task_input_artifact_versions.py -q` => `51 passed, 1 warning`. It proves the Worker sends the frozen payload only at runtime, records no raw attachment text in its event, keeps it out of checkpoint patches, and leaves no-attachment tasks independent of object storage.
- Attachment and workflow compatibility: `python -m pytest tests/modules/input_artifacts tests/integration/documents/test_document_tasks.py tests/integration/workflow/test_tasks.py -q` => `181 passed, 1 warning`. Undefined-name/import lint (`ruff --select F`) passed. Broader current suite including attachment and document integration => `566 passed, 6 skipped, 1 warning`. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **D1 is not approved and D2 must not start.** `docker compose config --services` has no S3-compatible object-storage service, and the tracked sample configuration leaves every `INPUT_ARTIFACT_OBJECT_STORAGE_*` value unset. The actual `S3ArtifactProcessingStorage` intentionally rejects that state. Consequently the tests prove mock/controlled contracts and the Worker consumption bridge, but not a real local upload object surviving scan/parse and becoming `ready`/consumable through the Compose runtime.
- The next D1 slice is limited to adding a local S3-compatible runtime plus a real, isolated upload-to-`ready`-to-Worker consumption proof (including storage-unavailable and checksum failure outcomes). It must preserve the existing no-attachment behavior and avoid treating a successful mocked parse as real object-storage E2E.

## 2026-10-10 — D1 automatic re-audit: local object-storage upload-to-consumption proof

### Real runtime slice

- Compose now supplies a pinned local S3-compatible service (`localstack/localstack:3.8.1`) and one-shot bucket initializer. API, Worker and Beat wait for that initializer before starting, and development-only object-store configuration is supplied only through Compose; no production credential or production object store is implied.
- The opt-in local E2E test creates an ordinary direct-upload session, submits its actual pre-signed multipart form to LocalStack (`201`), completes the session only after the S3 `HeadObject` checksum/length check, runs the received version through scan and parse jobs, writes immutable manifest/text objects, marks the version `ready`, freezes it on an analysis task, and reads the verified text into the runtime-only Planner attachment payload. It asserts the durable selection manifest contains no raw attachment text.
- The E2E scanner is deliberately deterministic-clean, so the state-machine proof is reproducible. Separately, the rebuilt Worker connected to the Compose ClamAV daemon and received `ScanResult(disposition='clean')` for a local probe. API configuration was also checked against a missing quarantined key and raised the expected `DirectUploadObjectNotFoundError`; an absent object cannot be accepted as consumable.
- The E2E deletes only its randomly created quarantine and parsed prefixes. After its run the local bucket reported no objects. LocalStack logs recorded the real `PostObject`, `HeadObject`, `GetObject`, `PutObject`, and cleanup calls.

### Verification

- `RUN_LOCAL_OBJECT_STORAGE_E2E=1 ../.venv-py313/Scripts/python.exe -m pytest tests/integration/input_artifacts/test_local_object_storage_e2e.py -q` => `1 passed, 1 warning`; this used the Compose LocalStack service and exercised the full object path above. The warning is the existing Starlette `TestClient` deprecation warning.
- D1-focused compatibility plus E2E => `225 passed, 1 warning`. The consolidated current-core, attachment, document, workflow, review and conversation suite with the same opt-in E2E => `567 passed, 6 skipped, 1 warning` in `33.70s`.
- `docker compose config --quiet` passed. API, Worker, Beat and LocalStack were rebuilt from the current source and remained running; LocalStack was healthy and its initializer exited successfully after creating `agent-artifacts`.
- The new E2E test and attachment-context module pass normal Ruff. Focused undefined-name/import checking across the D1 source and tests (`ruff --select F`) passes. The broader planning/test files still have pre-existing `FLY002`/`ISC004` style findings, which were not treated as D1 regressions. `git diff --check` found no whitespace error; it continues to emit pre-existing worktree-wide LF-to-CRLF conversion warnings.

### Automatic audit decision

- **D1 is approved for the local upload-to-consumption boundary.** A direct-upload object must pass storage metadata verification, scanning and parsing before a frozen `ready` version is supplied to Planner; its raw extracted text remains runtime-only and untrusted, while no-attachment tasks remain independent of object storage.
- **Scope limit:** this is Compose-local LocalStack, not browser UI/public-network delivery or a production object-store availability/SLA test. The direct-form request was sent by an integration client, not a browser. The end-to-end state transition uses a deterministic clean scanner; the separate ClamAV probe proves daemon connectivity and a clean reply, not malware-signature coverage, infected-file rejection, OCR/PDF production load, or an asynchronous Celery transport race. Those remain future failure/operations evidence and are not claimed here.

## 2026-10-10 — D2 automatic audit: analysis-task Outbox delivery state (not approved)

### Narrow correction and current proof

- The prior analysis-task Outbox used only `pending/published`; `published` was set as soon as `delay()` returned a Celery ID. This was Broker acceptance, not evidence that a Worker had atomically claimed an execution. The attachment-processing Outbox already used a stronger leased publication claim, which exposed the mismatch.
- Analysis-task events now use `pending → publishing → broker_accepted → worker_claimed`. A publisher obtains a generation-bound 30-second claim lease before it calls the Broker. A returned Broker message ID transitions only to `broker_accepted` and opens a 120-second delivery-observation lease. `claim_execution` records `worker_claimed` in its same transaction only after it has atomically changed the task from queued/retrying to running and created its execution attempt.
- An expired `broker_accepted` event becomes eligible for another publication. Duplicate delivery is expected at this boundary; the existing atomic task claim is still the sole authority for an effective Worker execution. Existing historical `published` rows are migrated cautiously: queued/retrying tasks become pending for recovery, while non-runnable historical tasks are marked legacy `worker_claimed` rather than replayed.

### Verification to date

- Targeted Outbox/execution/conversation suite => `23 passed, 1 warning`. It covers broker failure remaining pending, Broker acceptance not being Worker delivery, Worker claim recording its execution ID, and an accepted-but-unclaimed event becoming eligible for retry only after its delivery lease expires.
- The first migration attempt correctly failed because historical `published` rows violated the new check constraint. The corrected migration explicitly classified those rows before adding the constraint. `docker compose up -d --build migrate api worker beat` then completed; `alembic current` reports `t7e8f9a0b1c2 (head)`, and API/Worker/Beat are running from the rebuilt source.
- Consolidated current-core plus attachment/document/runtime E2E regression => `568 passed, 6 skipped, 1 warning` in `32.29s`. Focused undefined-name/syntax lint passes; `git diff --check` found no whitespace error apart from the existing worktree-wide LF-to-CRLF conversion warnings.

### Automatic audit decision

- **D2 is not approved and D3 must not start.** The new durable state boundary and simulated lease/republication contracts are verified, but a real Compose Worker interruption after Broker acceptance, followed by recovery/reconciliation and proof of one effective execution, has not yet been run. There is also no bounded operational metric or alert for overdue `broker_accepted` events. The next D2 slice must perform that controlled Worker-stop/restart drill without stopping PostgreSQL or the business database, then record delivery latency/recovery evidence and any failure limit.

## 2026-10-10 — D2 automatic re-audit: Worker-stop recovery drill

### Controlled runtime evidence

- The Compose Worker was stopped while PostgreSQL and Redis remained healthy. A dedicated task/event was created, and its first publication reached `broker_accepted` while there was no Worker consumer. Its delivery-observation lease was then deliberately expired and the same event was republished, yielding a second Broker message and `publish_attempt_count=2`.
- After the Worker restart, both messages were received. The first message atomically claimed task `136`, persisted execution `2f096543-eafa-41e5-91a3-cea6cbf8ba83`, and changed the Outbox event to `worker_claimed`. The second message logged that the task was already claimed, terminal, or missing. Database inspection confirms exactly one `TaskExecutionAttempt` and that its execution ID equals the Outbox `worker_execution_id`; the task completed once.
- PostgreSQL, Redis, API and Beat stayed running throughout; only the scoped Worker service was stopped and restarted. API, Worker, Beat and LocalStack are running after the drill.

### Important drill deviation

- The Worker claimed and completed the dedicated task faster than the post-claim stop command could take effect. It therefore made real configured model calls and the task completed; no duplicate execution or report was created. This is retained as a cost/audit fact, not hidden as a simulated result. The drill proves pre-claim Worker absence and duplicate-delivery suppression, but **does not** prove recovery from a process crash after an already-running execution has made model/tool calls; that is D3/D4 recovery scope.

### Automatic audit decision

- **D2 is approved for current Outbox delivery reconciliation.** Broker acceptance, Worker claim and business completion are now distinct facts; an unobserved delivery can be republished after a lease, and duplicate Broker delivery cannot create two effective execution attempts.
- **Scope limit:** no production queue availability, delay SLO, alerting, multi-Worker concurrency/load, or crash-after-side-effect recovery claim is made. The 120-second lease is a current controlled policy, not a measured RTO. D3 must test fencing/cancellation and late-execution writes before treating a running Worker crash as safe.

## 2026-10-10 — D3 automatic audit: cancellation revokes execution ownership (not approved)

### Confirmed correction

- Source audit found cancellation had set only `AnalysisTask.status='cancelled'`. Terminal writes were already fenced by `active_execution_id` plus `running` status, but the active ID remained and its `TaskExecutionAttempt` stayed `running`; a later expiry scan would revisit it indefinitely.
- `cancel_task` now atomically clears the task's active execution ID and marks its matching running attempt `cancelled` with a finish timestamp. Thus cancellation revokes the execution right before any late Worker can save state, terminal result, or a retry transition.
- New regression creates a claimed attempt, expires its lease, cancels it, then proves: active ID is absent; attempt is `cancelled`; expiry recovery returns no task; and the stale attempt cannot add a workflow-state checkpoint. Existing tests continue to prove stale attempts cannot finish or transition over a replacement execution.

### Verification to date

- D3-focused execution, Worker and conversation suite => `119 passed, 3 skipped, 1 warning`; changed source/tests pass Ruff and `git diff --check` has no whitespace error apart from existing LF-to-CRLF warnings.
- API, Worker and Beat were rebuilt from the current source and restarted successfully after the change.

### Automatic audit decision

- **D3 is not approved and D4 must not start.** The deterministic state-machine fence is now stronger, but no controlled running-Worker interruption has yet produced an old execution that attempts a late checkpoint/result write after a replacement claim or cancellation. That real concurrency/fault drill is required to prove the fence under process timing rather than only direct service calls.

## 2026-10-10 — D3 automatic re-audit: late Worker write fencing

### Two-process PostgreSQL race drill

- A dedicated old-execution process was started inside the Worker container. It atomically claimed task `138` and then paused. A separate API-container process expired that attempt's lease, ran recovery, atomically claimed a replacement execution, and persisted the replacement's `fresh` terminal result.
- The still-live old Worker process then resumed and tried both `checkpoint_workflow_state` and `finish_execution`. Both returned `False`. Final inspection shows task `138` is completed with `result_summary='fresh'` and replacement result data; it has exactly two attempts (`expired`, `completed`), and the old attempt has zero late Planner checkpoint rows.
- API, Worker, Beat, PostgreSQL and Redis were running after the drill. No LangGraph/model/tool call was made in this D3 drill; the two independent container processes exercised the real database conditional updates directly.

### Automatic audit decision

- **D3 is approved for current execution fencing and cancellation.** An expired/replaced execution cannot checkpoint, transition, or overwrite a replacement result; cancellation clears the execution right and terminalizes the matching attempt so expiry recovery does not revive it.
- **Scope limit:** this does not prove fencing for future external write tools, provider calls already sent before cancellation, multi-host clock skew, or all process-kill timings. Existing tools are controlled read-only; adding a side-effecting tool requires its own idempotency/unknown-write contract. D4 may now address checkpoint compatibility and resume boundaries.

## 2026-10-10 — D4 automatic audit: checkpoint compatibility and safe resume

### Verified compatibility contract

- Each new `WorkflowCheckpoint` now persists both `schema_version='workflow-checkpoint/v1'` and a SHA-256 fingerprint of the frozen task contract: question, company/data/schema snapshot identifiers, context/workflow/model policy snapshots, frozen document IDs, and frozen input-artifact-version IDs. Resume selects only a completed-node snapshot with both values matching the current task.
- Migration `u8f9a0b1c2d3` adds the non-null fields and marks the pre-existing 388 rows `legacy-unverified`. They are intentionally not resumed. Compose reports that migration as `head`; the runtime inspection observed 19 new v1 checkpoints after the drills.
- If no compatible stateful snapshot exists, the replacement starts from immutable inputs. A `checkpoint_resume_rejected` event on the replacement attempt records either `checkpoint_input_contract_changed` or `checkpoint_schema_version_incompatible`; no prompt, SQL, or document text is written into that event.

### Verification and controlled runtime drills

- Unit/integration regression: `python -m pytest tests/modules/workflow/test_task_execution_service.py tests/integration/workflow/test_tasks.py::test_worker_resumes_from_database_checkpoint -q` => `16 passed, 1 warning`. It covers a normal database resume plus rejection on a frozen task-contract change and unsupported checkpoint schema, including the durable rejection reason.
- Workflow regression: `python -m pytest tests/modules/workflow tests/integration/workflow -q` => `111 passed, 3 skipped, 1 warning`. Remaining project test groups ran as `383 passed, 3 skipped`, `78 passed`, and `48 passed, 1 skipped`; together with the workflow group this is `620 passed, 7 skipped`. The warning is the existing Starlette `TestClient` deprecation warning.
- Compose runtime drills used real PostgreSQL while Worker/Beat were intentionally stopped so no model call could consume the task. Task `143` resumed the compatible `data_node` checkpoint with its persisted plan. Tasks `142` and `144` changed the frozen input contract or checkpoint schema respectively; both restarted with no resume state and durably emitted the corresponding rejection reason. API, Worker, and Beat were restored and running afterwards.
- Focused Ruff for the D4 files passed and `git diff --check` found no whitespace error for those paths. Full `ruff check app tests` still reports many pre-existing, worktree-wide style findings; this audit does not claim a clean repository-wide lint baseline.

### Automatic audit decision

- **D4 is approved for the current checkpoint-resume boundary.** A replacement execution can reuse only a versioned checkpoint whose frozen input contract still matches; legacy, future-schema, and changed-input snapshots fail closed and leave an auditable reason.
- **Scope limit:** this does not prove compatibility across a real future application deployment with changed graph semantics, migration rollback of checkpoint data, external side effects already sent before a checkpoint, or multi-host recovery timing. The drills invoke execution persistence directly rather than interrupting a model/tool call at its exact return boundary. D5 may now address backup/restore RPO/RTO evidence.

## 2026-10-10 — D5 automatic audit: PostgreSQL backup and isolated restore drill

### Verified backup/restore contract

- `scripts/ops/backup-postgres.ps1` now emits a `postgres-backup-manifest/v1` beside every custom-format dump. It records dump name, byte size, SHA-256, UTC creation time, Alembic version, public-table count, and row counts for task, attempt, checkpoint, workflow-event, Outbox, and model-call ledger tables.
- `restore-drill.ps1` refuses application/test databases and any target not beginning `agent_platform_restore_`. Before it copies a dump or drops a drill target, it requires the adjacent manifest, verifies schema/name/SHA-256, and rejects a backup older than the declared local RPO target. After restore it compares Alembic version, table count, and each manifest row count, and fails if the elapsed restore time exceeds the declared local RTO target.
- The local drill objectives are explicitly frozen as RPO <= 15 minutes and RTO <= 900 seconds. They are acceptance bounds for this single-machine Compose drill, not a production SLA.

### Verification and controlled runtime drill

- PowerShell AST parsing for both operational scripts passed. `pytest tests/scripts/test_restore_drill_script.py -q` => `2 passed, 1 warning`; the tests prove checksum mismatch and an `agent_platform` target are rejected before any database action.
- With Worker and Beat stopped (PostgreSQL/Redis/API remained up), the backup script created `agent_platform_20261010_123859.dump` plus its manifest. The restore script restored it only into `agent_platform_restore_d5`, verified the manifest invariants, and measured `7.26` seconds with backup age `0` minutes. Worker and Beat were restored afterwards.
- Focused Ruff for the script test passed and `git diff --check` found no whitespace error in the D5 paths. The workspace-wide Ruff baseline remains non-clean because of pre-existing style findings outside D5; this entry makes no broader lint claim.

### Automatic audit decision

- **D5 is approved for the PostgreSQL logical-backup boundary.** A fresh, integrity-checked dump can be restored into an explicitly isolated database, and the task/execution/audit/accounting table populations and migration version match the backup manifest within the local RPO/RTO gate.
- **Scope limit:** this does not back up or restore LocalStack object originals, vector indexes, Redis transient state, external provider history, role/permission equivalence, or deletion/tombstone replay. It also does not prove point-in-time recovery, encrypted off-host retention, or a production RTO/RPO. Those are retained as P6-3/M4 work; D6 may now address clean rebuild, capacity, and backpressure.

## 2026-10-10 — D6 automatic audit: clean rebuild, readiness, initial concurrency (not approved)

### Verified operational corrections

- A clean `docker compose down -v` then `docker compose up -d --build` first exposed two reproducible initialization defects. PostgreSQL had been initialized as `SQL_ASCII` under the `C` locale; Compose now explicitly initializes it as UTF-8. The bootstrap script had installed `vector` only in `template1`, while Docker had already created `agent_platform` from the default template; it now installs the extension explicitly after connecting to `agent_platform`, without granting the application migrator superuser privileges. The final clean rebuild reports UTF-8 with `vector` installed, and Alembic reports `u8f9a0b1c2d3 (head)`.
- Stack verification now proves the real LocalStack bucket exists, the migration head is reachable from the API image, and both Celery workers reply to `inspect ping`; it passed after the rebuild. A LocalStack-only restart deliberately made readiness fail because the bucket had not been recreated. Re-running the one-shot `localstack-init` service restored the bucket and the verification passed. The runbook records that operational requirement.
- `/health/ready` now checks PostgreSQL, Redis, and configured object storage with bounded client timeouts. Controlled stops of Redis, LocalStack, and PostgreSQL each returned HTTP `503`; their healthy counterparts returned to ready after their dependency recovery. `live` remains a process check and is not used as dependency evidence.
- `inspect-queue.ps1` now reports live Redis list depth, Celery active/reserved/scheduled tasks and queues, plus durable analysis/artifact Outbox states. It no longer appends an unbounded historical log tail: a prior Redis-stop drill remained in that tail even while the current queue was empty, which was misleading rather than current health evidence. On the rebuilt stack, both queues were `0`, all Worker task states were empty, and overdue `broker_accepted` events were `0`.
- The roadmap's initial analysis concurrency boundary was not actually configured: both default Celery workers had started with concurrency/prefetch `16`. Compose now explicitly starts both `worker` and `report-worker` with `--concurrency=1`; `celery inspect stats` after their rebuild reports `max-concurrency=1` and `prefetch_count=1` for each. This is a safety baseline, not an inferred capacity claim.

### Narrow measurements and verification

- A temporary, isolated Worker on a dedicated queue processed 40 no-op Outbox publication ticks in `0.287s` at concurrency 1 and `0.219s` at concurrency 2 (about 139 and 182 tasks/s). The task found no pending events and created no business result, model request, tool call, or report. It is control-plane overhead evidence only.
- `python -m pytest tests/integration/observability tests/modules/observability tests/scripts -q` => `9 passed, 1 warning`. The warning is the existing Starlette `TestClient` deprecation warning. Focused Ruff for changed observability/script tests passed with the existing FastAPI `B008` dependency-injection exception excluded; `docker compose config --quiet` and relevant-path `git diff --check` passed, with only the repository's LF-to-CRLF warnings.

### Automatic audit decision

- **D6 is not approved and no later phase may start.** The clean rebuild, actual dependency readiness, queue visibility and explicit one-worker baseline are now evidenced, but they do not establish a capacity boundary or bounded overload behavior.
- **Required next D6 slice:** freeze an admission/backpressure contract before implementation (global and per-company queued/running limits, rejection/retry response, queue-wait/latency/cost observation window, and a safe target workload). Then prove it with a real scoped task path under controlled load, including recovery. Database-pool exhaustion, queue flood, disk-full/log retention, clock-skew/long-call behavior, resource peak, and a real Agent/model/tool workload remain unproved. The temporary no-op throughput numbers must not be used as customer capacity, P95, or SLO evidence.

## 2026-10-10 — D6 continuation: bounded task admission and local resource guards (not approved)

### Implemented protection boundaries

- New conversation messages and retry-created tasks now enter through a shared PostgreSQL transaction admission check before any task record is inserted. It counts only `queued`, `running`, and `retrying` tasks, serializes local admission with transaction-scoped advisory locks, and applies the initial conservative limits `5` per company and `20` globally. A rejection returns HTTP `429` with configured `Retry-After`; the conversation transaction rolls back, so no extra user/assistant message, task, or Outbox event survives. The 429 is also included in the existing payload-free company rejection audit path.
- The limits are explicit validated settings: task limits and retry delay must be positive; database pool size must be positive and `DATABASE_MAX_OVERFLOW` cannot be negative (which would otherwise permit unbounded SQLAlchemy overflow). The API and Worker runtime inspection reports `pool_size=5`, `max_overflow=10`, and `timeout=5` seconds.
- `inspect-queue.ps1` now reports durable in-flight task total, per-company in-flight counts, and oldest queued/retrying age in seconds alongside Broker and Outbox facts. The fresh Compose stack reported zero for all of these. Redis Celery queues still have no native `max_length`; bounded admission, rather than a Redis-key count, is the current task-ingress protection.
- Compose now applies Docker `json-file` rotation to every configured service (`max-size=10m`, `max-file=3`). Actual container inspection confirmed the policy on API, both Workers, PostgreSQL, and Redis. This bounds container stdout/stderr growth only; it does not cap database, object-store, or application-data volumes.
- Lease, Outbox-delivery, recovery, checkpoint, transition, completion, and cancellation timestamps now obtain an aware timestamp from PostgreSQL `clock_timestamp()` through one shared helper. This is deliberate: a live transaction probe showed `CURRENT_TIMESTAMP` stayed fixed across `pg_sleep(1)`, while `clock_timestamp()` advanced. Therefore transaction-start time is not used for a long-running lease decision. A later source audit found the Worker cancellation branch and duration calculation still used its local wall clock; both now use the same helper, with a regression test that fixes the database clock and verifies the persisted cancellation time and duration.
- An Outbox event that has not reached an effective Worker claim now has a terminal `cancelled` state. Task cancellation atomically moves only `pending`, `publishing`, or `broker_accepted` events to that state, clears its publication lease, and records `task_cancelled_before_worker_claim`; an already `worker_claimed` event is left intact. Migration `v9a0b1c2d3e4` applies the database constraint. This closes the prior recovery loop in which a cancelled `broker_accepted` event became eligible for republishing after its lease.
- Before a real-workload run, the live configuration was found to have an empty price table, so cost budget checks would have reserved zero monetary cost. The local configuration and example now freeze the provider's conservative peak, cache-miss Flash rate under version `deepseek-v4.1-flash-peak-2026-10-10`: `$0.0003` prompt and `$0.0012` completion per 1K tokens for the configured legacy `deepseek-v4-flash` name. The provider states that this legacy name routes to V4.1 Flash and is billed at Flash pricing; peak cache-miss is intentionally used as an upper bound rather than assuming a cache hit or off-peak rate. A live no-network reservation probe for 100 prompt plus 200 completion tokens produced the expected `$0.00027` reserved amount with its price key/version, then deleted its temporary task, attempt, call ledger, and user.

### Verification

- The HTTP integration case sets company limit `1` and global limit `2`, accepts the first message, rejects the second with `429`/`Retry-After`, proves only the first task/Outbox/two messages remain, and observes the company rejection audit. A separate real PostgreSQL test starts two independent Sessions concurrently for one company and proves exactly one admission succeeds while the other is limited.
- The admission-focused suite previously passed as `17 passed, 1 warning`. After the database-clock correction, burst-recovery addition, and cancelled-Outbox state, the relevant workflow, conversation, observability, settings, and script regression suite passed as `144 passed, 3 skipped, 1 warning`; the warning is the existing Starlette `TestClient` deprecation warning. Focused Ruff excluding the existing project-wide `B008`, `BLE001`, and `TRY004` convention debt passed for every touched Python file.
- A real PostgreSQL admission/recovery test starts eight independent Sessions for one company with a limit of three: exactly three tasks are admitted and five are limited. It then cancels the three queued tasks through the production cancellation function and proves a new task is admitted. This establishes release of an admission slot after a terminal cancellation; it deliberately does not send a Broker message or invoke a model.
- A real API-container probe with only one available database connection (`pool_size=1`, `max_overflow=0`, `timeout=1`) held that connection and received the expected `TimeoutError` on the second request in one second. The probe process exited and released its connection; it did not alter the running service or business data.
- After rebuilding API, both Workers, and Beat with the corrected clock helper, `verify-stack.ps1` passed: PostgreSQL, Redis, LocalStack bucket, migration head, and two Celery nodes were healthy. `inspect-queue.ps1` showed zero Broker backlog, zero durable in-flight tasks, and zero oldest-pending age; the Worker inspection still reported `max-concurrency=1` and `prefetch_count=1`. The live API helper returned a UTC-aware PostgreSQL timestamp, and PostgreSQL itself reported `Etc/UTC`.
- After the Worker-side timestamp correction, both Worker images were rebuilt again and `verify-stack.ps1` again passed with PostgreSQL, Redis, LocalStack, the migration head, and both Celery nodes healthy.
- A live Compose drill stopped the ordinary Worker before submitting six real authenticated HTTP messages for a newly created, isolated company. With the configured company limit of five, it accepted five and returned `429` for the sixth. The five accepted messages had real `broker_accepted` delivery records, then were cancelled through the conversation API; all five task and Outbox records became `cancelled` before Worker restart. After restart, the Worker consumed the five already-enqueued messages, but created zero execution attempts and zero model calls; task and Outbox states remained `cancelled`. The final Broker depth, Worker active/reserved/scheduled lists, durable in-flight count, and overdue Broker-accepted count were zero. The generated user, company, conversation, task, Outbox, source, and snapshot records were then queried as absent after scoped cleanup.
- The post-configuration Compose recreation loaded one price-table entry in the API container. The no-network reservation probe persisted `pricing_key=deepseek-v4.1-flash-peak-cache-miss`, the frozen price-table version, `billing_status=reserved`, and `reserved_cost=0.00027`, then deleted its entire generated graph. This demonstrates that a future task snapshot can enforce a nonzero conservative reservation; it does not prove provider-reported usage or final settlement.

### Automatic audit decision

- **D6 remains not approved; no later phase may start.** These changes bound request admission, log output, and database-pool waiting, but do not establish a measured Agent capacity or SLO.
- **Still required:** a pre-frozen real read-only Agent workload measured at concurrency 1 then candidate 2, with task/node P95, queue wait, memory, timeout and cost observation; a non-cancelled Worker-stop/recovery workload; safe disk-full behavior for database/object/application volumes; and injected host/database clock-skew and long-model-call failure behavior. The database-authoritative clock is a source-level mitigation, not a completed clock-skew fault drill. The Session-level and live cancellation bursts prove admission and cancelled-message recovery only, not successful Agent capacity, long-running work recovery, or customer capacity. **The full application-authorization/RLS/tenant-pool proof remains required final scope, but belongs to deferred E1 and is not a D6 precondition.** No claim is made for production availability or any untested fault path.

## 2026-10-11 — D6 continuation: local `business_db` ten-task concurrency 1/2 measurement (not approved)

### Environment and fixed workload

- The requested local `business_db` was first inspected: it contained zero public business tables and no configured read-only role, so it could not honestly support a read-only Agent run. Its dedicated local volume was then initialized with the repository's deterministic demo seeder. The database now contains 22 public tables; `business_readonly` was verified to have `rolsuper=false`, `rolcreaterole=false`, `rolcreatedb=false`, `rolbypassrls=false`, and no INSERT/UPDATE/DELETE/TRUNCATE privilege on any public table. This is an initialization action on the explicitly selected disposable local demo database, not evidence about a customer database.
- Ten authenticated HTTP conversation-message requests used the same frozen data-only question, `比较华东区2025年7月与8月已交付订单销售额。`, no document or attachment scope, the same source configuration (`business_db` / `business_data` / `business_readonly`), and the same 22-table Schema Snapshot fingerprint `78c5a968904b2bf48c103f42edccfec4702033308148294367d48b1d0eb47c65`. Before either Worker was enabled, each five-task batch was audited as queued with zero execution attempts and zero model calls, then its persisted budget snapshot was set to `max_calls=8`, `max_calls_per_node=3`, `max_repairs=1`, `max_total_tokens=8000`, and `max_cost=$0.01`. This gives `$0.10` aggregate reserved-task budget under the user's `$0.15` authorization; it is not a general multi-task global-budget ledger.

### Measurements

| Fixed workload (five tasks each) | Concurrency 1 baseline | Concurrency 2 candidate |
|---|---:|---:|
| Terminal status | 5 `partial/model_budget_exhausted` | 5 `partial/model_budget_exhausted` |
| Attempt mean / P95 / max | 5303.0 / 7348.0 / 8005.0 ms | 5970.6 / 8031.4 / 8067.7 ms |
| Queue wait from actual Worker container start, mean / P95 | 16570.0 / 25553.5 ms | 9662.1 / 15585.1 ms |
| Settled model calls / unknown calls | 20 / 0 | 20 / 0 |
| Settled model cost | `$0.013391` | `$0.013551` |
| Successful `sql_query` tool calls | 1 | 1 |
| Planner / semantic-review / data node P95 | 3761.8 / 1268.6 / 1376.4 ms | 4483.0 / 1015.4 / 1529.3 ms |

- Aggregate settled cost was `$0.026942`, below the authorized `$0.15`; no call had unknown billing state or residual reservation. The candidate execution-attempt intervals proved maximum concurrent work `2`, and runtime sampling observed its Worker memory from `132.1 MiB` to `508.5 MiB` (nine samples; interpolated sample P95 about `508.5 MiB`).
- The concurrency-1 sampler was delayed by Compose dependency startup and captured only one post-run memory observation (`332.3 MiB`), so it does **not** establish a baseline memory P95 or a valid memory comparison. Do not infer a capacity gain: on this five-task sample, concurrency 2 shortened queue wait but had worse task P95 (8031.4 ms vs 7348.0 ms) and planner P95 (4483.0 ms vs 3761.8 ms).
- Both batches reached the configured read-only source and had one successful scoped SQL tool call, but the remaining tasks exhausted the deliberately conservative per-task model budget before completion. Therefore this is a real Agent/model/Worker cost-and-concurrency measurement, **not** ten successful SQL business analyses and not business-quality or customer-capacity proof. The model-budget exhaustion is a useful Bad Case: the `$0.01` per-task constraint is insufficient for this current four-call-to-partial path.
- After extracting the measurements above, the temporary Worker-concurrency-2 container was removed and the ordinary Compose Worker was restored with `max-concurrency=1` and `prefetch_count=1`. Both temporary users, companies, sources, snapshots, conversations, messages, tasks, Outbox rows, attempts, model-call rows, and tool-call rows were deleted by their exact generated identifiers and queried as absent. The retained local `business_db` demo source remains at 22 tables. Final queue inspection reported Broker queues `0`, no active/reserved/scheduled Worker tasks, zero durable in-flight tasks, and zero overdue broker-accepted events.

### Automatic audit decision

- **D6 remains not approved; no later phase may start.** The requested 10-task 1/2 comparison is now measured under its stated cost ceiling, but it does not meet the D6 exit bar: the baseline memory P95 was not captured, the workload did not complete successful business analyses, and the sample is too small to establish an SLO or a concurrency-2 benefit.
- **Still required:** repeat a pre-frozen workload with complete comparable resource sampling and a cost policy that can complete its intended read-only business path; a non-cancelled Worker-stop/recovery workload; safe disk-full behavior for database/object/application volumes; and injected host/database clock-skew and long-model-call failure behavior. Full application-authorization/RLS/tenant-pool proof remains deferred E1 scope, not a D6 precondition. This run does not alter the prior limits on production or customer-capacity claims.

## 2026-10-11 — D6 correction: task-frozen output reservation (not approved)

- The failed capacity run exposed a reproducibility gap: a task saved model name, timeout, price table, and total budget, but did not save the configured `max_output_tokens`. Both provider gateways read that value from the live Worker environment, so a later environment change could alter a queued task's request ceiling and pre-call reservation.
- New tasks now save `model_policy_snapshot.max_output_tokens`. While a governed task scope is active, DeepSeek and OpenAI gateways use that frozen positive integer consistently for request `max_tokens`, completion-token reservation, and persisted request provenance. Legacy rows without the field retain the old gateway-configured fallback; no historical task is rewritten.
- Regression verification: `pytest tests/modules/runtime/test_model_gateway.py tests/modules/runtime/test_model_gateway_factory.py tests/modules/runtime/test_model_governance_contract.py tests/modules/runtime/test_model_governance.py tests/integration/workflow/test_task_admission.py -q` => `31 passed, 1 warning`. The new cases prove task creation freezes the configured value and both provider gateways use it inside a task scope even when their live configured limit differs. Focused Ruff passed. API and Worker were rebuilt and recreated from the new source; `verify-stack.ps1` passed with the migration head and both Worker pings healthy.
- **D6 remains not approved.** This closes one configuration-drift cause of an invalid future comparison but makes no model call, does not provide a completed workload, and does not replace the missing comparable memory/timeout/recovery/fault evidence.

## 2026-10-11 — D6 measurement-runner hardening (not approved)

- Added `scripts/ops/measure-agent-capacity.ps1`, a deliberately narrow observer for an already-created task batch. It refuses a non-running Worker, captures the actual Worker container start time, samples Docker memory and durable task status until every requested task reaches a terminal state, then emits `agent-capacity-measurement/v1` JSON with sample count, P95/peak memory, attempt P95, queue-wait P95, settled cost, and unknown-call count. It does not create tasks, change Worker concurrency, call a model, or write a result artifact.
- The script has PowerShell AST validation and a source-contract regression test (`1 passed, 1 warning`; focused Ruff passed). A real smoke used a disposable already-terminal task: it emitted one memory sample (`180459930` bytes), zero settled and unknown cost, and null attempt/queue percentiles as expected for a task with no attempt. That temporary task and user were then deleted by exact ID and confirmed absent; final queue inspection was zero across Broker, Worker active/reserved/scheduled, and durable in-flight state.
- **D6 remains not approved.** The runner prevents the earlier baseline-sampling blind spot but cannot turn the previous budget-exhausted workload into a successful business-capacity result. A new paid comparison still needs explicit user budget authority.

## 2026-10-11 — D6 corrected local `business_db` concurrency 1/2 measurement (not approved)

### Workload qualification and measurement correction

- The original Chinese workload was not valid for this frozen demo contract: `华东区` did not match the stored region `华东`, and `sales_orders.status` has the contract value `delivered`, not the unproven Chinese literal. A first corrected wording without the status filter was also correctly rejected by `revenue/v1`, which requires `sales_orders.status = delivered`; a second wording with `华东区` and `delivered` executed SQL but returned no records. These are retained Bad Cases, not failed capacity results: their settled costs were `$0.016040`, `$0.015127`, and `$0.003092`, respectively, with zero unknown calls.
- A read-only source check then established the actual demo facts: `sales_orders` contains only `delivered` status, the region is `华东`, and the requested 2025-07/08 cells contain `2014010.64` and `1847604.72`. A real preflight using `比较区域名称为“华东”的2025年7月与8月、状态为 delivered 的订单销售额。` executed scoped SQL and completed with those two values. A command-escaping error left that preflight task's persisted budget at its default `$1.00`; although its actual settled cost was only `$0.003408`, it is explicitly excluded from the controlled comparison.
- `measure-agent-capacity.ps1` now accepts `WaitForWorkerSeconds`, so an observer can be launched before a Worker and use the actual container start time. PowerShell AST validation, the script source-contract test, and Python Ruff passed (`1 passed, 1 warning`). A real preflight measurement obtained four samples from queued through terminal state, proving the wait path; its temporary output files were removed after inspection.

### Final frozen 5+5 comparison

- Both batches used the same local `business_db` source, the same 22-table snapshot fingerprint `78c5a968904b2bf48c103f42edccfec4702033308148294367d48b1d0eb47c65`, the same qualified question above, no document or attachment scope, the same frozen output cap (`1024`), and per-task snapshot `max_calls=8`, `max_calls_per_node=3`, `max_repairs=1`, `max_total_tokens=14000`, `max_cost=$0.02`. Each task was audited queued with zero model calls before its Worker was started. Beat remained stopped and the ordinary Worker was stopped between batches; only Worker concurrency changed.

| Qualified five-task workload | Concurrency 1 baseline | Concurrency 2 candidate |
|---|---:|---:|
| Terminal result / successful scoped SQL | 5 `completed` / 5 | 5 `completed` / 5 |
| Attempt P95 | 6317 ms | 9404 ms |
| Queue-wait P95 from actual Worker start | 27404 ms | 18179 ms |
| Batch wall time from Worker start | 34192 ms | 25033 ms |
| Memory samples / P95 / peak | 14 / 326.6 / 326.6 MiB | 10 / 510.4 / 510.4 MiB |
| Settled cost / unknown calls | `$0.017170` / 0 | `$0.017926` / 0 |
| Planner / semantic-review / data / reviewer P95 | 1537 / 986 / 1341 / 1435 ms | 1435 / 1249 / 1282 / 1632 ms |

- All ten persisted result payloads contain the exact independently queried values `2014010.64` and `1847604.72`; the comparison therefore proves this one deterministic local read-only business path, not broader answer quality or customer capacity. The final 10-task settled cost was `$0.035096`; all continuation attempts (including Bad Cases and preflights) settled `$0.072763`. Together with the earlier `$0.026942` run, observed spend is `$0.099705`, below the user-authorized `$0.30` total. The accidental unfrozen preflight is recorded above and not treated as a hard-cap proof.

### Automatic audit decision

- **Do not adopt concurrency 2.** It shortened the five-task batch by about 26.8% and queue-wait P95 by about 33.7%, but worsened attempt P95 by about 48.9%, raised sampled memory P95 by about 56.3%, and cost about 4.4% more. The ordinary Compose Worker remains the concurrency-1/prefetch-1 baseline.
- **D6 remains not approved; no later phase may start.** This closes the earlier missing comparable-sampling and successful-workload evidence for one local workload. It does not establish an SLO or customer capacity, and the non-cancelled Worker-stop/recovery workload, disk-full behavior, and host/database clock-skew and long-model-call drills remain required. The final RLS/tenant-pool boundary proof remains deferred E1 scope.

## 2026-10-11 — D6 real non-cancelled Worker-stop recovery drill (failed, not approved)

- A new isolated HTTP task used the qualified read-only `business_db` workload and a frozen `$0.02` budget. After one Planner request reserved `$0.0016638`, an enter-stage marker was present; the ordinary Worker was then forcibly killed (container exit `137`) without cancelling the task. The task remained `running` under its old execution ID and the old attempt remained `running`, as expected before lease recovery.
- The old lease was explicitly made expired in the local test database and the real Celery recovery task requeued the work. A second attempt with a new execution ID completed the task and the existing Outbox row remained a single `worker_claimed` record, so old execution ownership did not publish a duplicate result.
- **Correction to the initial interpretation:** that row was not a completed Planner snapshot. `tasks._update_stage` writes it before entering `planner_node`, with `state_patch={"stage":"planning"}` and `next_node="planning"`; `_latest_resume_checkpoint` deliberately excludes it because it lacks `workflow_state`. Therefore recovery correctly restarted Planner and the two Planner calls do not prove duplicate execution after a completed Planner node. A valid completed-node recovery drill must wait for a checkpoint with `workflow_state` and `next_node="planner_semantic_review_node"` before killing the Worker.
- **Hard-gate failure:** the first Planner model-call ledger row remains `billing_status=reserved` with no settlement timestamp after the kill. The new task completed with `reserved_cost=$0.0016638` still present and `unknown_cost_calls=0`; recovery did not convert an interrupted external request to unknown cost. The second attempt's five calls settled normally. This must be repaired before another recovery drill; neither the final answer nor the clean Outbox row compensates for duplicate model work or unaccounted uncertainty.
- The interrupted request adds a possible `$0.0016638` provider charge to the earlier observed `$0.099705`, so the conservative cumulative spend bound is `$0.1013688`, still below the user-authorized `$0.30` ceiling. It is deliberately not reported as settled cost.
- The temporary user/company/source/snapshot/conversation/task graph was removed after this evidence was retained. **D6 remains not approved and no later phase may start.** Required corrective slice: terminally mark stale reserved model calls as unknown while retaining their reservation, add regression coverage, then repeat two distinct real drills: one kill during a reserved provider call (no residual `reserved` ledger row) and one kill after a completed-node `workflow_state` checkpoint (no repeated completed node and no duplicate publication).

## 2026-10-11 — D6 recovery ledger repair and repeat drills (recovery slice approved; D6 not approved)

- `recover_expired_executions` now locks each expired attempt's still-`reserved` `ModelCallRecord` rows and terminally writes `billing_status=unknown`, `result_category=unknown`, `error_code=execution_lease_expired_before_settlement`, and the recovery timestamp. It increments `unknown_cost_calls` exactly once while deliberately retaining `reserved_cost`; an interrupted provider request is therefore never represented as free or silently left in the nonterminal `reserved` state.
- The focused regression creates an expired attempt with a reserved provider row, proves the row becomes unknown with a settlement time and preserved reservation, and proves a second recovery pass cannot increment uncertainty again. The cross-boundary suite `pytest tests/modules/workflow/test_task_execution_service.py tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_settlement_integration.py tests/integration/workflow/test_tasks.py::test_worker_resumes_from_database_checkpoint -q` passed: `30 passed, 1 warning`; focused Ruff passed. The warning is the existing Starlette `TestClient` deprecation warning.
- The first repeated real local `business_db` drill used the same qualified frozen read-only workload and `$0.02` task cap. A container-internal 50ms observation caught task 42's real Planner ledger row while it was `reserved` (`$0.001685`), then killed the ordinary Worker (exit 137). After explicit local test-lease expiry and the real Celery recovery task, old attempt 37 was `expired`, its row was `unknown` with the new error code and timestamp, `unknown_cost_calls=1`, and its reservation remained charged. New attempt 38 completed. One Outbox row remained `worker_claimed`.
- The second drill waited specifically for task 43's Planner completion checkpoint: `completed_node=planner_node`, `next_node=planner_semantic_review_node`, and `state_patch` containing `workflow_state`. The Worker was then killed after Semantic review had begun but before it settled. Recovery expired attempt 39, marked only that interrupted Semantic review row unknown, and completed attempt 40. The persisted call counts were Planner `1`, Semantic review `2`, data `2`, reviewer `1`: the completed Planner node was not rerun. The task still had exactly one `worker_claimed` Outbox row.
- A preliminary task 41 completed before an earlier host-side watcher could observe the short reservation window; it is not recovery evidence. Its settled `$0.003247` is included in accounting. Tasks 41–43 settled `$0.009888` and retained `$0.003380` across two unknown reservations. With the earlier observed `$0.099705` and the original interrupted `$0.0016638` conservative reservation, the conservative cumulative provider-cost bound is `$0.114637`, below the user-authorized `$0.30` total ceiling.
- All temporary task/user/company/source/snapshot records and dependent attempt, model-call, checkpoint, and Outbox rows were deleted by exact IDs and queried absent. Beat and the Worker were restored. `verify-stack.ps1` passed; `inspect-queue.ps1` reported Broker `celery=0`, `reports=0`, no active/reserved/scheduled work, and durable in-flight total `0`.

### Automatic audit decision

- **The Worker-stop recovery/unknown-billing corrective slice is approved. D6 remains not approved; no later phase may start.** These tests prove this one external-call interruption accounting path and completed-node resume path on the local demo only.
- **Still required for D6:** safe disk-full handling for database/object/application volumes; injected host/database clock-skew and long-model-call behavior; and a broader, repeated workload sample before any SLO or customer-capacity claim. Full RLS/tenant-pool boundary proof is deferred E1 scope. The successful local recovery drills do not prove those boundaries.

## 2026-10-11 — D6 application ENOSPC retry classification (not approved)

- Source inspection found `process_analysis_task` classified every `OSError` as retryable. Therefore an application-level `ENOSPC` would enter its bounded Celery retry path, adding avoidable work while storage remains exhausted. The Worker now excludes only `errno.ENOSPC`; timeout, connection, other OS failures, and retryable model errors keep their existing retry behavior.
- The injected PostgreSQL integration test makes `run_analysis` raise `OSError(ENOSPC, ...)`, proves one attempt reaches terminal `failed` with no retry, and preserves the existing transient connection and model-retry contracts. `pytest tests/integration/workflow/test_tasks.py::test_worker_does_not_retry_disk_full_error tests/integration/workflow/test_tasks.py::test_worker_retries_transient_connection_error tests/integration/workflow/test_tasks.py::test_worker_retries_retryable_model_error tests/modules/workflow/test_task_execution_service.py -q` passed: `21 passed, 1 warning`; focused Ruff and `git diff --check` passed. The warning is the existing Starlette `TestClient` deprecation warning.
- This is an injected application-error proof, not a real database, Docker-volume, or object-store full-disk drill. Compose log rotation limits container stdout/stderr, but no current per-volume quota or low-watermark admission control protects PostgreSQL or LocalStack. Filling the shared host/Docker disk is intentionally not used as a test substitute.

### Automatic audit decision

- **D6 remains not approved; no later phase may start.** The Worker now fails a surfaced application `ENOSPC` safely rather than adding retry pressure. Actual capacity thresholds and safe failure/recovery behavior for database and object-store volumes, plus the remaining clock/long-call and broader capacity evidence, are still unproved. Full RLS/tenant-pool proof is deferred E1 scope.

## 2026-10-11 — D6 frozen provider-timeout lease bound (not approved)

- The prior task snapshot saved `timeout_seconds`, but both provider Gateways still used the live Worker setting. The setting had only a positive-value check, so a later configuration change could make a queued task's provider call outlive the 120-second execution lease, which has no in-call heartbeat.
- New configuration rejects an LLM timeout above 60 seconds, leaving at least half of the current 120-second lease for bounded failure/recovery. During a governed call, DeepSeek and OpenAI now read the task-frozen timeout for both the SDK request and persisted request provenance; a legacy snapshot without this field falls back to the already validated live default, while a malformed frozen value fails before provider contact.
- Regression verifies both Gateway implementations send the frozen timeout rather than a changed live timeout and ledger it in model parameters; settings reject `61` and accept `60`. The focused suite `pytest tests/modules/runtime/test_model_gateway.py tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_governance_contract.py tests/modules/system/test_settings.py tests/integration/workflow/test_tasks.py::test_worker_does_not_retry_disk_full_error tests/integration/workflow/test_tasks.py::test_worker_retries_transient_connection_error -q` passed: `34 passed, 1 warning`; focused Ruff and `git diff --check` passed. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **D6 remains not approved; no later phase may start.** This prevents configuration drift from creating a provider timeout at or beyond the current lease. It is not a real provider-hang or host/database clock-skew drill, does not add an in-call heartbeat, and does not prove behavior if a client or network ignores its timeout.

## 2026-10-11 — D6 model-ledger database-clock alignment (not approved)

- A post-recovery clock audit found that Workflow leases, checkpoints, Outbox transitions, and task transitions already use PostgreSQL `clock_timestamp()`, but `record_model_call` still assigned `settled_at` from the Worker host wall clock. This did not change lease expiry semantics, but it could make cross-Worker model-ledger ordering and audit time subject to host-clock skew.
- Model-call settlement now obtains `settled_at` through the same database clock helper. The regression uses a controllable database-clock result and proves the persisted settled ledger row uses that value; gateway fallback test doubles now supply the same minimal `scalar()` database-clock contract.
- Verification after the change: `pytest tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_settlement_integration.py tests/modules/runtime/test_model_gateway.py tests/modules/workflow/test_task_execution_service.py -q` => `43 passed, 1 warning`; focused Ruff passed; `git diff --check` passed. The warning is the existing Starlette `TestClient` deprecation warning. The Worker was rebuilt and recreated; `verify-stack.ps1` passed, and `inspect-queue.ps1` reported `celery=0`, `reports=0`, no active/reserved/scheduled tasks, and durable in-flight total `0`.

### Automatic audit decision

- **The model-ledger clock-alignment slice is approved. D6 remains not approved; no later phase may start.** It removes one Worker-host timestamp from persisted model accounting, but is not an injected host/database clock-skew drill and does not prove an SDK/network long-call failure path. Safe database/object/application-volume disk behavior and broader repeated capacity evidence remain unproved; full RLS/tenant-pool proof is deferred E1 scope.

## 2026-10-11 — D6 execution-lease/provider-timeout invariant (not approved)

- The prior 120-second execution lease and 60-second maximum provider timeout had the intended relationship but were separate literals. A future lease-only edit could silently permit a provider request to consume the whole recovery window.
- Both values now derive from one core execution-lease constant: `MAX_LLM_TIMEOUT_SECONDS` is exactly half of `EXECUTION_LEASE_SECONDS`, while Workflow keeps its existing `LEASE_SECONDS` alias for compatibility. Runtime behavior is unchanged at 120/60 seconds; the change makes the safety relationship mechanically visible and regression-tested.
- Verification: `pytest tests/modules/system/test_settings.py tests/modules/runtime/test_model_gateway.py tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_settlement_integration.py tests/modules/workflow/test_task_execution_service.py tests/integration/workflow/test_tasks.py::test_worker_does_not_retry_disk_full_error tests/integration/workflow/test_tasks.py::test_worker_retries_transient_connection_error -q` => `51 passed, 1 warning`; focused Ruff and `git diff --check` passed. The Worker was rebuilt and recreated. `verify-stack.ps1` passed; `inspect-queue.ps1` reported `celery=0`, `reports=0`, no active/reserved/scheduled tasks, and durable in-flight total `0`.

### Automatic audit decision

- **The lease-timeout invariant slice is approved. D6 remains not approved; no later phase may start.** This prevents a particular future configuration/code drift but does not create an in-call heartbeat or prove behavior when a provider client or network disregards its timeout. The remaining real volume-full, clock-skew/long-call, and broader-capacity boundaries are unchanged; full RLS/tenant-pool proof is deferred E1 scope.

## 2026-10-11 — D6 application-volume ENOSPC response (not approved)

- The application-level Worker retry fix did not cover the API's legacy local document-file path. Source review found that a target-volume `ENOSPC` removed a partial file but escaped as an indistinguishable generic 500 response.
- The local document storage path now maps an `ENOSPC` from directory creation or target-file writing to `InsufficientStorageError`; its API boundary returns a stable HTTP `507` with code `insufficient_storage` and a safe Chinese retry-later message. Other OS errors retain their original behavior. This does not add a retry or leave a document record behind.
- The injected target-write test writes one byte, raises `ENOSPC`, then proves the quarantine/upload directory is empty. The API contract test injects that typed failure and proves its `507` response. `pytest tests/modules/documents/test_storage.py tests/modules/documents/test_document_upload_api.py tests/integration/documents/test_documents.py tests/integration/workflow/test_tasks.py::test_worker_does_not_retry_disk_full_error -q` => `13 passed, 1 warning`; focused Ruff excluding the module's existing FastAPI `B008` convention and `git diff --check` passed. The warning is the existing Starlette `TestClient` deprecation warning. API was rebuilt and recreated; `verify-stack.ps1` passed and `inspect-queue.ps1` found both queues empty, no active/reserved/scheduled tasks, and durable in-flight total `0`.
- A stronger isolated runtime drill used the rebuilt `agent-api` image with a disposable `1 MiB` Docker `tmpfs` mounted at `/app/storage`, then attempted to store a `2 MiB` document with a permitted `4 MiB` application limit. The kernel returned real `ENOSPC`; the process observed `InsufficientStorageError`, proved the upload directory had no partial file, printed `real_tmpfs_enospc_cleanup=passed`, and exited. The container used `--rm`, did not join the Compose network, and left no persistent host, database, object-store, or application-volume data.

### Automatic audit decision

- **The local application-volume ENOSPC response slice is approved. D6 remains not approved; no later phase may start.** This is a typed source/API proof plus an isolated real-kernel `tmpfs` fault for the legacy local document volume only. It does not establish a low-watermark or quota, and does not cover the persistent PostgreSQL volume or browser-direct S3/LocalStack capacity failure.

## 2026-10-11 — D6 gate correction and repeated concurrency-1 sample (not approved)

- Re-reading the authoritative execution order found an evidence-ledger error: full application-authorization/RLS/tenant-pool proof had been listed as a D6 prerequisite, although the core-first plan deliberately places that strengthening in deferred E1. Keeping it as a D6 blocker creates a D6-to-E1 cycle. Every D6 audit entry now retains it as required final scope but marks it deferred E1, without weakening the existing RLS/readonly boundaries or claiming E1 complete.
- A first repeat batch of five authenticated HTTP tasks ran the same qualified `business_db` read-only question under the same 22-table snapshot fingerprint and a pre-execution `$0.015` per-task hard cap. A failed in-process observer handoff meant that batch is cost/success evidence only: all five completed, settled `$0.017107`, and had zero unknown calls, but it is not used for P95 or memory comparison.
- A second five-task concurrency-1 batch used an independently started observer that began before Worker startup. It produced 14 samples from all queued to all terminal: task-attempt P95 `6428.1502 ms`, queue-wait P95 `26957.0358 ms`, memory P95 `342611722` bytes (`326.7 MiB`), peak `342884352` bytes (`327.0 MiB`), settled cost `$0.017848`, and zero unknown calls. All five tasks completed. This is directionally consistent with the prior concurrency-1 five-task result (`6317 ms`, `326.6 MiB`, `$0.017170`), but two small samples are not an SLO or a concurrency-2 adoption decision.
- The temporary owner, company, source, snapshot, ten conversations, ten tasks, and all task-cascaded attempts/model-call/tool-call/checkpoint/Outbox records were deleted by exact generated IDs and queried absent. Beat was restored; queue inspection showed no Broker backlog, no active/reserved/scheduled tasks, and zero durable in-flight tasks. The temporary observer artifact was removed.

### Automatic audit decision

- **D6 remains not approved; no later phase may start.** The repeated valid concurrency-1 observation reduces uncertainty about that one baseline but does not repeat the concurrency-2 candidate, set an SLO, or establish capacity. Persistent PostgreSQL and object-storage full-volume behavior and injected clock-skew/long-client-call behavior remain D6 gaps. Full application-authorization/RLS/tenant-pool proof remains required final scope in E1, not a D6 prerequisite.

## 2026-10-11 — D6 repeated concurrency-2 execution (observer failure, not a comparison)

- A same-contract five-task concurrency-2 run used a temporary Worker with `--concurrency=2`, while the ordinary Worker and Beat were stopped. All five authenticated, frozen `$0.015`-cap tasks completed with zero unknown calls and total settled cost `$0.016802`.
- The pre-start observer produced no terminal measurement artifact despite task completion, so this run has no trustworthy Worker-start timestamp, sample series, memory P95, or queue-wait P95. It is retained only as real success/cost evidence and is deliberately excluded from concurrency-performance comparison or adoption.
- The temporary Worker was stopped and removed. The exact task graph, source, snapshot, company, conversations, and user were deleted and the ordinary Worker and Beat restored. Final queue inspection had no Broker backlog, no active/reserved/scheduled tasks, and zero durable in-flight tasks.

### Automatic audit decision

- **D6 remains not approved; do not adopt concurrency 2.** The valid repeated concurrency-1 observation remains the only new performance-quality sample. The observer failure itself is a measurement-tool Bad Case to correct before another paid candidate run; persistent PostgreSQL/object-store volume faults and clock-skew/long-client-call behavior remain D6 gaps.

## 2026-10-11 — D6 repaired-observer repeated concurrency-2 sample (not approved)

- The two preceding candidate batches are retained only as success/cost evidence because their observers failed: first on a missing Worker container that `$ErrorActionPreference = "Stop"` treated as terminal despite stderr redirection, then because the caller passed an `int[]` value through `powershell -File` as one comma-delimited string. The runner now catches the missing-container probe for its configured wait window and accepts comma-delimited positive task IDs, parsing them to integer IDs before querying. Its focused source-contract regression and PowerShell AST parse passed; an already-terminal no-model-call smoke confirmed the returned `task_ids` are integers and the normal JSON schema is emitted. This correction does not turn either invalid candidate run into a measurement.
- The final candidate created five fresh authenticated HTTP tasks against the same qualified 22-table local `business_db` snapshot fingerprint `78c5a968904b2bf48c103f42edccfec4702033308148294367d48b1d0eb47c65`, exact read-only question, no attachments, frozen output cap `1024`, and per-task hard cap `$0.015`. Before its Worker began, all five were `queued`, had zero attempts and zero model calls. The corrected observer was started before the temporary concurrency-2 Worker; it remained alive with no stderr output and recorded eight samples from five queued tasks through all terminal.

| Qualified five-task observation | Repeated concurrency 1 baseline | Repaired concurrency 2 candidate |
|---|---:|---:|
| Terminal result / expected two sales values | 5 completed / present | 5 completed / present |
| Observation samples | 14 | 8 |
| Attempt P95 | 6428.2 ms | 9323.6 ms |
| Queue-wait P95 from actual Worker start | 26957.0 ms | 17467.2 ms |
| Sampled memory P95 / peak | 326.7 / 327.0 MiB | 509.6 / 509.6 MiB |
| Settled cost / unknown calls | `$0.017848` / 0 | `$0.016825` / 0 |

- Every final-candidate result contained the independently checked `2014010.64` and `1847604.72`; each had five settled model calls and no unknown call. The observer samples show at most two `running` tasks at a time, matching the intended candidate concurrency. The candidate reduced sampled queue-wait P95 by about 35.2%, but worsened task P95 by about 45.0% and raised sampled memory P95 by about 56.0%. Its small-sample cost difference is not a capacity conclusion. It therefore fails the adoption criterion: ordinary Worker concurrency 1/prefetch 1 remains the baseline.
- Actual cumulative measured spend, including all retained Bad Cases and observer-failure batches, is `$0.217149`, below the explicitly authorized `$0.30` ceiling. The temporary Worker and exact generated five tasks, conversations, source/snapshot, company, and user were deleted and queried absent before the ordinary Worker and Beat were restored.

### Automatic audit decision

- **The repaired-observer slice is approved; D6 remains not approved, and concurrency 2 is not adopted.** It supplies one valid repeated concurrency-2 comparison point for this local workload, not an SLO, customer-capacity estimate, durable global budget, or broader workload result. Persistent PostgreSQL and object-storage volume-full behavior plus injected clock-skew/long-client-call behavior remain D6 gaps. Full application-authorization/RLS/tenant-pool proof remains final E1 scope, not a D6 prerequisite.

## 2026-10-11 — D6 isolated PostgreSQL and object-storage capacity drills (not approved)

- The current running Compose PostgreSQL and `localstack_data` volumes were deliberately not filled. Instead, each drill used a separately named disposable container and an isolated Docker `tmpfs`; no Compose service, data volume, task, model call, or customer/demo business row was modified.
- PostgreSQL drill: a 16 MiB `tmpfs` could not even initialize PostgreSQL, so it was rejected as a non-diagnostic limit. A fresh 64 MiB `tmpfs` instance initialized, accepted twelve independent approximately 512 KiB incompressible `bytea` inserts, then the thirteenth produced the real server failure `PANIC: 53100 ... pg_wal/xlogtemp... No space left on device` and disconnected the client. The container's main PostgreSQL process exited and Docker's `--rm` cleanup removed the `tmpfs`. This establishes that a WAL-capacity event can terminate the database process; it does **not** prove persistent-volume restart/recovery, and the application cannot safely claim that it persisted a terminal task state when its database cannot write.
- Object-storage drill: source inspection found LocalStack 3.8.1 writes S3 objects under `/tmp/localstack-s3-storage`, not `/var/lib/localstack`; an initial 96 MiB limit on the wrong directory therefore accepted an isolated 128 MiB object and was discarded as a configuration-discovery Bad Case. A second fresh LocalStack with a 96 MiB `tmpfs` on the actual S3 directory rejected an isolated 128 MiB `PutObject` after client retries with `InternalError` and `[Errno 28] No space left on device`; `ListObjectsV2` returned no `Contents`, while the LocalStack process remained alive. This proves a real object-write failure is not silently reported as successful and leaves no listed object in this emulator.
- Both disposable containers were removed by exact name. Afterwards `verify-stack.ps1` passed: normal PostgreSQL, Redis, LocalStack bucket, migration head, API, Worker, Beat, and both Celery pings were healthy. `inspect-queue.ps1` reported `celery=0`, `reports=0`, no active/reserved/scheduled tasks, zero durable in-flight tasks, and zero overdue broker-accepted events.

### Automatic audit decision

- **D6 remains not approved; no later phase may start.** These are genuine kernel/storage failures, but not the missing production-style safety mechanism. There is still no tested low-watermark/admission policy for persistent PostgreSQL or object-store capacity, no persistent-volume recovery evidence after PostgreSQL WAL exhaustion, and no application E2E that can retain truthful terminal/audit state across a database write failure. The unresolved injected clock-skew and long-client-call boundaries remain separate D6 gaps. No cost-bearing model call was made by either drill.

## 2026-10-11 — D6 timeout ledger-to-Worker retry chain (not approved)

- A missing link in prior evidence was tested directly against the migrated test PostgreSQL database: a governed Worker call first writes its durable model reservation, a simulated provider timeout settles that same record as `unknown` with `provider_timeout` and no fabricated cost, then the Worker persists `retrying`. The new integration regression proves `unknown_cost_calls=1`, `ModelCallRecord.billing_status=unknown`, `cost is null`, a database-clock settlement timestamp, and task `retrying` state in one chain. It deliberately injects the timeout before any external request; it makes no paid model call and does not claim a real provider outage.
- The focused timeout/clock suite passed `6 passed, 1 warning`: frozen gateway timeout conversion, unknown-not-zero-cost accounting, the new durable Worker chain, database-clock lease creation, and a real PostgreSQL `clock_timestamp()` advance within one transaction. Ruff passed for the changed test and `git diff --check` found no whitespace error. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **The timeout-accounting-to-retry slice is approved; D6 remains not approved.** It establishes the intended accounting/state behavior for an injected provider timeout and confirms the core lease path uses database time rather than Worker wall clock. It does not alter host or database clocks, create an in-call heartbeat, prove a client that ignores its timeout, or demonstrate a recovery after a real long-running provider request. Those fault boundaries, along with persistent-volume capacity recovery, remain D6 work.

## 2026-10-11 — D6 real local slow-provider timeout (not approved)

- The prior injected `APITimeoutError` test was strengthened with a standard-library, loopback-only HTTP server. Its handler waits 1.5 seconds before responding; a real OpenAI-compatible SDK client receives the task-frozen one-second timeout, sends one request, times out before the delayed response, classifies it as `RetryableModelError/provider_temporary_error`, and persists `timeout_seconds=1` in request provenance. The test does not use a provider key beyond a dummy value, does not reach the network beyond `127.0.0.1`, and makes no paid call.
- The first implementation used total wall time as its threshold and caught only `BrokenPipeError`; a diagnostic reproduction showed one real request, with about 0.5 seconds of local connection/thread scheduling before the one-second read timeout, and Windows may surface the disconnected response write as `ConnectionAbortedError`. The final assertion therefore measures from handler receipt, accepts the expected socket `OSError`, and keeps a broad total-wall-time guard. This is a test-stability correction, not a product timeout change.
- Timeout conversion, local slow response, and durable Worker unknown-accounting/retry chain passed `3 passed, 1 warning`; Ruff passed for both changed tests and `git diff --check` passed. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **The local slow-provider timeout slice is approved; D6 remains not approved.** It proves the frozen SDK request timeout against a real local socket delay and its bounded state/accounting transition. It still cannot prove Internet/provider behavior, a client that ignores its timeout, an in-call heartbeat, or a physical host/database clock adjustment. Persistent PostgreSQL/object-storage capacity recovery remains unproved.

## 2026-10-11 — D6 isolated PostgreSQL capacity-release recovery (not approved)

- A Docker `tmpfs` persistence probe first proved that data survives a restart of the *same* container. Based on that fact, a fresh isolated PostgreSQL container kept its failed data directory alive under a supervising shell rather than using `--rm`. A 32 MiB explicitly named capacity-reserve file was created outside PostgreSQL's managed files; it represents space an operator can release, not a database-file deletion.
- With the reserve present, twelve committed approximately 512 KiB incompressible inserts succeeded. The thirteenth caused the same real `PANIC: 53100 ... pg_wal/xlogtemp ... No space left on device`; PostgreSQL attempted crash recovery, then failed its startup because only 12 MiB remained. The exact reserve file was still present. No cleanup or mutation was attempted through the failed database.
- The simulated operator action removed only the isolated reserve file, raising free space from 12 MiB to 44 MiB. PostgreSQL was then started against the same data directory, completed recovery, retained `12` committed rows (`6968 kB` relation size), and accepted a new thirteenth one-byte row. The disposable container was removed by exact name. This proves the operational order: free/extend capacity outside the database first, then restart/recover; it does not prove that a full database can persist a task failure before capacity is restored.
- The normal Compose stack was untouched. After cleanup, `verify-stack.ps1` passed and `inspect-queue.ps1` reported both queues at zero, no active/reserved/scheduled tasks, zero durable in-flight tasks, and zero overdue broker-accepted events.

### Automatic audit decision

- **The isolated PostgreSQL capacity-release recovery slice is approved; D6 remains not approved.** It is stronger than a bare ENOSPC injection: it contains real WAL exhaustion, failed automatic recovery, an external capacity-release action, successful recovery, and data continuity. It remains an in-container `tmpfs` exercise rather than the normal Compose persistent volume, does not cover object-store recovery after capacity release, and does not make an application-level final-state claim while PostgreSQL is unable to write. The long-client/clock limitations remain unchanged.

## 2026-10-11 — D6 isolated object-store capacity release and LocalStack persistence audit (not approved)

- A fresh, same-container LocalStack S3 drill used a 128 MiB `tmpfs` on its real object directory and an explicitly named 48 MiB reserve file. A 96 MiB upload hit real `[Errno 28]`, returned S3 `InternalError`, and left no listed object. Releasing only the reserve file restored 48 MiB. After a restart, the emulator could create a bucket and write/head a fresh 1 MiB object, so capacity release restored service availability.
- That is **not data recovery**. The pre-failure bucket did not exist after restart. A separate isolated probe supplied `PERSISTENCE=1`, `SNAPSHOT_SAVE_STRATEGY=ON_REQUEST`, and `SNAPSHOT_LOAD_STRATEGY=ON_STARTUP` to the pinned `localstack/localstack:3.8.1` image. The running container received all three variables, but `/var/lib/localstack/state` remained without snapshot files, `POST /_localstack/state/s3/save` returned `404`, and a bucket/object written before restart returned `404` after it. This is authoritative behavior of the currently pinned image, even though current LocalStack documentation describes snapshot persistence for newer/runtime-supported configurations; no unverified upgrade or Compose setting was applied.
- All temporary LocalStack containers were removed by exact name. The normal Compose stack was then verified healthy: PostgreSQL, Redis, its normal LocalStack bucket, migration head, API, Worker, Beat, and both Celery pings passed; both queues were zero with no active/reserved/scheduled or durable in-flight tasks.

### Automatic audit decision

- **D6 remains not approved; no later phase may start.** Object-store capacity release now has a real emulator service-recovery proof, but the pinned local emulator cannot provide its claimed restart-data recovery path. Treat its S3 objects as ephemeral across restart for this project version. A deliberate, separately validated LocalStack version/runtime persistence upgrade or an alternative persistent S3-compatible test backend is required before claiming object-store recovery. The normal Compose persistent PostgreSQL volume, application-level database-full state handling, and long-client/clock limitations remain independent D6 gaps.

## 2026-10-11 — D6 persistent S3-compatible backend candidate audit (rejected)

- Three isolated alternatives were tested before changing the normal Compose stack. The locally cached `minio/minio:RELEASE.2024-10-13T13-34-11Z` completed the project's generated pre-signed POST, `HeadObject`, and same-container restart readback, but a newer official MinIO community tag listed by Docker Hub could no longer be pulled at runtime. The current locally available AIStor image started but rejected `CreateBucket` with an expired-license error. Neither is a reproducibly fetchable, license-free local dependency for this repository.
- `chrislusf/seaweedfs@sha256:84429e5f21fad82246f5cfae7b39e9a17da18afb62f2b79c25ccd364ab02793b` then passed the isolated pre-signed POST, `HeadObject`, named-volume restart readback, and the complete upload -> scan -> parse -> frozen attachment consumption E2E when temporarily mapped to the same host port. A Compose candidate also created its bucket from a fresh named volume, passed the same E2E before and after an object-store restart, and read a probe object before deleting it. These are real compatibility observations, not adoption evidence by themselves.
- The candidate is rejected: a normal restart emitted `volumeDataIntegrityChecking failed verifyDeletedNeedleIntegrity ... EOF` for several local object volumes and marked them non-writable during reload. Current upstream source treats the same path as a volume-data-integrity failure, and its public restart-recovery issue records the same diagnostic together with no-writable-volume behavior after a forced shutdown. This local run did not prove the identical cause or customer-data loss, but a storage integrity diagnostic during the required recovery drill is sufficient to reject the backend rather than normalize it.
- The exact SeaweedFS container and its candidate-only `agent_object_storage_data` volume were removed after rollback. Compose returned to the pinned LocalStack service and its preserved existing volume; normal bucket readiness, API/Worker/Beat startup, `verify-stack.ps1`, queue inspection, and the default local object-storage E2E all passed. `verify-stack.ps1` now fail-fast checks every Docker Compose command, including the real LocalStack bucket lookup; it does not change application behavior.

### Automatic audit decision

- **The candidate investigation is approved and the SeaweedFS replacement is rejected. D6 remains not approved; no later phase may start.** The evidence narrows the object-storage decision without making an unsupported persistence claim. The pinned LocalStack restart-data gap remains open, and the persistent PostgreSQL-volume, application database-full, and long-client/clock gaps remain separate D6 work. No model call or model cost was incurred by this candidate audit.

## 2026-10-11 — D6 current LocalStack persistence-upgrade probe (rejected)

- The locally available `localstack/localstack:latest` was inspected as digest `sha256:0c644ede65c2d0c95737e09a39007828bd381bdb07ca8200c6bf17d66a4ed191` (reported version `2026.9.1`, build date `2026-10-07`). A fresh isolated named-volume container supplied only its S3 service, development credentials, and `PERSISTENCE=1`; it exited before exposing S3 with code `55`, explicitly requiring `LOCALSTACK_AUTH_TOKEN` for license activation. No bucket or object was created.
- The exact failed container and its empty named volume were removed. The normal pinned `3.8.1` Compose service remained separate and unchanged.

### Automatic audit decision

- **The current LocalStack upgrade is rejected for the local no-new-authority scope; D6 remains not approved.** A token/license could be a valid future product decision, but it is not inferred from the existing task authorization. The pinned emulator's restart-data gap and the independent D6 capacity/clock gaps remain open.

## 2026-10-11 — D6 database-full terminal-transition recovery contract (not approved)

- A new real-test-PostgreSQL Worker regression separates application storage ENOSPC from database-write ENOSPC. It first claims and persists a normal `running` execution, then injects `OSError(ENOSPC)` precisely where the generic error path would atomically transition task/attempt/checkpoint/event to a terminal failure. The injected write failure propagates; it does not fabricate a `failed` task, clear `active_execution_id`, or mark the attempt terminal.
- After the injected capacity condition is removed, the test expires that still-owned lease and invokes the normal recovery routine. It persists `retrying` and clears the active execution ID, proving the safe order is capacity recovery -> lease recovery -> retry, rather than a false final state while PostgreSQL cannot write. This is an injected persistence-boundary test over the migrated test database; it does not claim a real full persistent PostgreSQL volume can retain any new terminal/audit row.
- The focused D6 suite passed `69 passed, 1 warning`, covering model timeout/governance, Worker transition/recovery, and this new regression. `verify-stack.ps1` passed against normal PostgreSQL, Redis, LocalStack, API and both Workers; queue inspection found no active/reserved/scheduled or durable in-flight work. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **The database-full terminal-transition slice is approved; D6 remains not approved.** It closes the false-terminal-state ambiguity at the Worker state-machine boundary, but does not replace persistent-volume capacity admission/recovery evidence, object-store restart data recovery, or a physical clock/long-client-call drill. No model call was made.

## 2026-10-11 — D6 isolated named-volume PostgreSQL capacity-release recovery (not approved)

- A stronger PostgreSQL drill used an exact disposable Docker named volume, but mounted a 115 MiB ext4 loopback filesystem stored inside that volume. This creates a real bounded persistent filesystem without allocating/filling host disk or touching the normal Compose `postgres_data` volume. Mount capability was proven by an explicit marker surviving an independent helper-container remount.
- The first capacity-reserve attempt used `truncate`; `du` reported `0` and `df` was unchanged, proving it was sparse and non-diagnostic. It was replaced with a real `fallocate` 32 MiB reserve, reducing free space to 28 MiB before any workload write. That configuration correction is retained rather than treating a nominal file size as consumed capacity.
- PostgreSQL initialized on the bounded filesystem, and independent autocommit inserts of incompressible approximately 512 KiB `bytea` values produced the real server error `could not extend file ... No space left on device`. The server later also logged `FATAL: could not write init file`. Twenty-two committed rows occupied `12 MB`; no normal Compose database, business database, task, customer row, or model call was modified.
- Removing only the named reserve file restored 32 MiB free. Restarting the same database container against the same loopback image performed automatic WAL recovery, retained all `22` committed rows, and accepted a new 23rd one-byte insert. The exact disposable container and its named volume were removed. Normal stack verification and queue inspection then passed with no active/reserved/scheduled or durable in-flight tasks.

### Automatic audit decision

- **The named-volume PostgreSQL capacity-release slice is approved; D6 remains not approved.** It upgrades the earlier tmpfs result to a persistent Docker-volume-backed filesystem and proves recoverable committed data across capacity release and restart. It is still a loopback filesystem inside a disposable volume, not the normal Compose PostgreSQL volume; it does not prove object-store restart data recovery, database-full application writes, low-watermark admission policy, or physical clock/long-client behavior. No model cost was incurred.

## 2026-10-11 — D6 late long-call result fencing after lease recovery (not approved)

- Source tracing confirms the execution lease is extended by stage and workflow-checkpoint writes. The blocking `run_analysis(...)` call itself has no independent heartbeat. This is a source fact, not an inference from the test.
- A new migrated-test-PostgreSQL concurrency regression starts a Worker on a controlled blocking no-network `run_analysis` stub, waits until the model-call boundary has been entered, expires its running execution from an independent database session, and invokes the normal lease-recovery routine. It then releases the old Worker to return a terminal answer. The recovered task remains `retrying`, has no active execution ID, and retains neither `result_data` nor `result_summary`; the expired attempt cannot publish its late answer. The test makes no provider call and spends no model budget.
- The D6 focused suite passed `70 passed, 1 warning`. The new late-result test passed again after a test-only lint correction; Ruff passed. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **The late-result fencing slice is approved; D6 remains not approved and no later phase may start.** It proves that a recovered lease fences an old Worker's delayed terminal write, so a late result cannot overwrite the recovery state. It does **not** cancel a request already inside `run_analysis`, prevent a replacement Worker from issuing a second external request, provide an in-call heartbeat, or test a physical clock change. Therefore it must not be described as duplicate-cost prevention or full long-client-call recovery. Persistent object-store restart data recovery, persistent-volume application capacity behavior, low-watermark admission, and clock-fault evidence remain separate D6 gaps.

## 2026-10-11 — D6 independent execution heartbeat during blocking workflow (not approved)

- The prior late-result test exposed a concrete source gap: execution leases were renewed only by stage/checkpoint writes, so a synchronous blocking `run_analysis(...)` could consume the lease without a checkpoint. The Worker now starts a daemon heartbeat only while the governed workflow is running. Each tick creates its own `SessionLocal`; it never shares the Worker Session across threads.
- `renew_execution_lease` locks the attempt, rejects an expired/non-running attempt, then locks and verifies the active `running` task ownership before setting `heartbeat_at` and a new lease using PostgreSQL time. It refuses to revive an expired execution. The expiry recovery path now locks each candidate attempt and rechecks its lease after the lock before releasing its task. This removes the race in which recovery selected an old expiry while a heartbeat was extending it.
- Regressions cover a successful live renewal, rejection of an expired renewal, dynamic interval derivation (`lease/3`, minimum one second), and a migrated-test-PostgreSQL concurrent Worker whose controlled blocking workflow runs beyond a two-second test lease. The independent heartbeat renews first, normal recovery returns no task, and the workflow then completes with its expected answer. No external provider, model key, or paid call is used.
- Verification: workflow/integration tests passed `48 passed, 1 warning`; the D6 model/runtime/workflow suite passed `74 passed, 1 warning`; Ruff passed for every changed Python file. The warning is the existing Starlette `TestClient` deprecation warning.
- The actual Compose analysis Worker was rebuilt and recreated from this source. A runtime import confirmed the default 40-second heartbeat interval; `verify-stack.ps1` passed for PostgreSQL, Redis, LocalStack, migration head, API, and both Celery nodes. Queue inspection reported `celery=0`, `reports=0`, no active/reserved/scheduled work, zero durable in-flight tasks, and zero overdue broker-accepted events.

### Automatic audit decision

- **The independent long-call heartbeat slice is approved; D6 remains not approved and no later phase may start.** A healthy Worker can now retain its execution ownership during a blocking workflow, and expiry recovery no longer races a successful renewal. This does not interrupt an already-sent provider/tool request when the Worker loses database access or is cancelled, make an unknown external side effect idempotent, prove a physical host/database clock change, or replace the unresolved persistent object-store restart-data, persistent-volume application-capacity, and low-watermark-admission evidence. No production/SLO claim follows from this local regression.

## 2026-10-11 — D6 RustFS persistent S3 candidate audit (rejected)

- The candidate was investigated only in an isolated Docker container at host port `19000` with a candidate-only named volume. The pulled `rustfs/rustfs:latest` image was digest `sha256:1803faef57627e2d9c2e7d89d655d712ddded5389040054987163043fecb6a3c`; its own `--version` reported `rustfs 1.0.1`. A private candidate bucket was created using non-production candidate credentials; the normal Compose LocalStack service and its volume were never changed.
- The project generated its actual pre-signed POST form, uploaded the exact test payload, and received HTTP `201`. The subsequent real `HeadObject(ChecksumMode=ENABLED)` returned the expected content length but no `ChecksumSHA256`; `S3DirectUploadStorage.inspect_quarantine_object` therefore raised `DirectUploadObjectIntegrityError`. The normal upload-session finalizer correctly returned the terminal rejection rather than allowing an object without verifiable SHA-256 into scan/parse. This identifies an S3 metadata-contract failure, not an application defect.
- The LocalStack-only E2E test now permits explicit endpoint/bucket/credential environment overrides while preserving its prior defaults. It was run against the candidate to produce the failure and then against normal LocalStack, where upload -> checksum verification -> scan -> parse -> frozen attachment consumption passed `1 passed, 1 warning`. Ruff passed for the changed test. The warning is the existing Starlette `TestClient` deprecation warning.
- The exact candidate container and its named volume were removed after the test. No candidate object, customer/demo data, normal S3 bucket, or paid model call remains.

### Automatic audit decision

- **The RustFS investigation is approved and the RustFS replacement is rejected. D6 remains not approved and no later phase may start.** The candidate is persistent-capable in principle, but it fails this project's non-negotiable direct-upload integrity contract before restart recovery can be relevant. Do not weaken the checksum verification simply to adopt a backend. The pinned LocalStack restart-data limitation and remaining D6 capacity/admission/clock boundaries are unchanged.

## 2026-10-11 — D6 isolated Worker/database clock-skew fault drill (not approved)

- A disposable container was created from the current analysis-Worker image on the existing Compose network, with a process-only `libfaketime` preload. Its own Python clock was fixed at `2035-01-02 03:04:05 UTC`; the normal PostgreSQL service, normal Worker, host clock, business databases, and Compose volumes were not modified. The probe imported the actual Worker task module so SQLAlchemy model registration matched the production entrypoint.
- Within that skewed Worker process, the actual `claim_execution` path created a temporary user/task/attempt against the normal platform PostgreSQL. The process observed year `2035`, while the persisted attempt heartbeat and lease base were PostgreSQL year `2026`; the lease was later than that database timestamp. The probe deleted its exact temporary task and user before exit. This is direct runtime evidence that claim/lease state is not derived from the Worker's wall clock.
- The first probe command did not enter Docker because PowerShell split the timestamp argument; the second and third attempts exposed incomplete standalone SQLAlchemy model registration before the actual Worker module was imported. Those command/setup failures made no database write and are retained as drill diagnostics, not represented as application failures. The successful probe ran only after reproducing the real module-registration path.
- The exact `agent-d6-faketime-worker` container was removed. Afterwards `verify-stack.ps1` passed for PostgreSQL, Redis, LocalStack, migration head, API, and both Celery nodes. Queue inspection found `celery=0`, `reports=0`, no active/reserved/scheduled work, zero durable in-flight tasks, and zero overdue broker-accepted events.

### Automatic audit decision

- **The Worker/database clock-skew lease slice is approved; D6 remains not approved and no later phase may start.** It proves a material process-clock skew cannot move the persisted claim heartbeat or lease base away from PostgreSQL time. It does not alter the real host or PostgreSQL clock, cover all timestamps outside the traced execution/model paths, simulate a clock jump during an active long call, or replace persistent-object-store recovery and capacity/admission evidence.

## 2026-10-11 — D6 heartbeat database-failure recovery boundary (not approved)

- A migrated-test-PostgreSQL concurrent Worker regression reduces the lease to two seconds, starts a controlled blocking workflow, and makes every independent heartbeat renewal raise `ConnectionError`. The test waits for that actual renewal attempt, lets the unrenewed lease expire, invokes normal recovery, and only then releases the old workflow result.
- Recovery returns the task exactly once, changes it to `retrying`, clears its active execution ID, and leaves `result_data`/`result_summary` empty after the old Worker returns. The heartbeat exception is therefore fail-closed for execution ownership: it does not fabricate liveness or permit the late result to publish. The test uses no external provider or model budget.
- Verification: the new regression passed independently; changed-test Ruff passed; the D6 model/runtime/workflow suite passed `75 passed, 1 warning`. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **The heartbeat database-failure recovery slice is approved; D6 remains not approved and no later phase may start.** It proves the new heartbeat does not weaken fencing when its separate database session fails. The old in-flight workflow still cannot be forcibly interrupted and an external provider request may remain `unknown`; persistent-object-store restart recovery, persistent-volume capacity/admission, and broader workload evidence remain independent D6 requirements.

## 2026-10-11 — D6 isolated persistent-volume real Worker/database-full recovery (not approved)

- A fresh 192 MiB ext4 loopback filesystem was created inside the exact disposable Docker named volume `agent_d6_app_db_loop`. PostgreSQL ran against that mounted persistent filesystem on a separate Docker network; the current Worker image connected to it with a fresh migrated `agent_platform` database. The normal Compose PostgreSQL, LocalStack, Workers, queues, business databases, and volumes were not used.
- An initial mount directly onto PostgreSQL's data directory was rejected by `initdb` because ext4's expected `lost+found` made it nonempty. The volume itself was healthy; remounting it at PostgreSQL's parent directory allowed the entrypoint to create an empty `data` subdirectory. This configuration Bad Case is retained rather than treating the first failed bootstrap as a capacity result.
- After all migrations, the bounded filesystem had 113 MiB free. A real non-sparse `fallocate` reserve consumed 64 MiB, leaving 49 MiB. The actual Worker first atomically claimed a real task. Its controlled no-network workflow used an independent PostgreSQL connection to insert 512 KiB random `bytea` records until the server returned `DiskFull` after 36 committed inserts, then raised `OSError(ENOSPC)` through the real Worker error path. PostgreSQL logged `PANIC: could not write to file pg_wal/xlogtemp ... No space left on device`; the Worker's terminal-transition write raised `OperationalError` rather than fabricating a terminal task state.
- PostgreSQL's automatic recovery failed while the reserve remained. Removing only that external reserve file raised free space to 76.9 MiB; restarting the same PostgreSQL data directory completed WAL recovery. Before recovery, the real task and attempt were both `running` with matching active execution ownership. After expiring that lease, the normal `recover_expired_executions` function returned the task once and persisted `retrying` with no active execution ID. A new recovery marker table/row then committed, proving restored write ability. The exact filler table, marker table, task, and user were deleted before teardown.
- The exact disposable PostgreSQL container, Docker network, and named volume were removed. Normal `verify-stack.ps1` passed afterwards; queue inspection reported `celery=0`, `reports=0`, no active/reserved/scheduled work, zero durable in-flight tasks, and zero overdue broker-accepted events. No external model call or paid cost occurred.

### Automatic audit decision

- **The isolated real Worker/database-full recovery slice is approved; D6 remains not approved and no later phase may start.** This is stronger than injected storage exceptions: it joins a real bounded persistent filesystem, actual PostgreSQL WAL exhaustion/recovery, the real Worker claim/error path, and truthful task recovery after external capacity release. It remains an isolated disposable volume rather than the normal Compose database volume; it does not prove an advance low-watermark admission policy, object-store restart data recovery, customer data durability, or a production capacity/SLO boundary.

## 2026-10-11 — D6 persistent object-store decision boundary (not approved)

- The remaining object-store gate is precise: a replacement must pass the project's generated pre-signed POST upload, reject an invalid signed-policy constraint, return a matching SHA-256 through `HeadObject(ChecksumMode=ENABLED)`, complete scan -> parse -> frozen-attachment consumption, and retain that validated object after a named-volume restart. A successful S3-compatible upload alone is insufficient.
- The currently available candidates do not meet that contract under the existing local authority: pinned LocalStack loses the needed restart-data evidence; current LocalStack requires an unavailable license token; RustFS supplied no verifiable SHA-256 for the project's direct-upload contract; SeaweedFS exposed a restart-integrity warning; and S3Mock does not validate signed-policy constraints. MinIO was not reproducibly available from a supported public image in this environment. These are rejection or evidence facts, not reasons to weaken checksum or policy enforcement.
- The next valid path requires new, explicit authority: either a user-supplied LocalStack token/license kept out of logs, restricted credentials for an isolated S3-compatible test bucket, or a reproducibly sourced backend image selected/provided by the user. Any path must run the full five-part contract above and record its teardown and residual limits before reconsidering D6.

### Automatic audit decision

- **D6 remains not approved and no later phase may start.** There is no honest local-only substitute for persistent object-store restart evidence that preserves both the signed-policy and checksum boundaries. The decision is recorded rather than bypassing the gate with a permissive mock or reduced integrity check.

## 2026-10-11 — D6 capacity/backpressure observability boundary audit (not approved)

- Current task backpressure is deliberately scoped to queued/running/retrying task counts: `_admit_task(...)` serializes admission with PostgreSQL advisory locks and applies global and company in-flight limits. It prevents a task burst from exceeding its configured count, but it neither reads nor can infer free space in PostgreSQL or an S3-compatible object-store volume.
- Current application-storage capacity handling is reactive and correctly typed: `save_document_file(...)` removes its partial legacy local file after a surfaced `ENOSPC`, and the upload API maps the resulting `InsufficientStorageError` to HTTP `507`. This is a local application-volume failure contract; it does not provide a pre-write low-watermark for the database or direct-upload object store.
- Existing `measure-agent-capacity.ps1` is an observer, not an admission mechanism: it samples a pre-created batch's Worker memory, task terminal state, attempt latency, queue wait and settled/unknown call accounting. The focused contracts passed `7 passed, 1 warning` across concurrent task admission, the measurement-script guard, upload `507`, and partial-file cleanup. The warning is the existing Starlette `TestClient` deprecation warning. No model call, task creation, or configuration change occurred in this audit.

### Automatic audit decision

- **The capacity/backpressure boundary audit is approved; D6 remains not approved and no later phase may start.** Implementing a guessed application-side disk threshold would be unsafe because the API process has no authoritative free-space observation for the PostgreSQL or S3 backing volumes. A future low-watermark admission control must consume an authenticated backend-specific capacity signal and fail closed on an unavailable signal; it cannot substitute for the still-required persistent object-store restart contract.

## 2026-10-11 — D6 direct-upload public/internal endpoint repair (not approved)

- Root cause: the Compose API/Worker correctly use the internal `localstack` service name for S3 calls, but `S3DirectUploadStorage.create_quarantine_upload_form(...)` also embedded that internal-only name in browser-facing pre-signed POST URLs. A host/browser-equivalent upload consequently failed DNS resolution before any object write. API-container `HeadBucket` access was healthy, so this was a network-view/configuration defect rather than a credential or bucket failure.
- The storage configuration now has an optional public endpoint used only to create the pre-signed POST. Direct-upload finalization (`HeadObject`) and processing Worker reads/writes keep using the internal endpoint. Compose sets the public local development endpoint to `127.0.0.1:4566`; absent configuration preserves the old single-endpoint behavior. Bucket, credentials, exact-size policy, SHA-256 requirement, and Worker storage path are unchanged.
- Verification: unit/settings contracts passed `8 passed, 1 warning`; a real API-container-to-host probe produced valid upload `201`, exact-size policy violation with an otherwise correct SHA-256 `400`, and internal `HeadObject` length/SHA-256 verification. Its two exact probe objects were deleted. The opt-in real S3 E2E passed `2 passed, 1 warning` for upload -> checksum verification -> scan -> parse -> frozen attachment consumption and signed-policy rejection; related regression selection passed `12 passed, 2 skipped, 1 warning` (the two opt-in E2E tests were intentionally skipped in that non-opt-in selection). Ruff, Compose config validation, rebuilt API stack verification, and empty queue inspection passed. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **The public/internal direct-upload repair is approved; D6 remains not approved and no later phase may start.** It closes a real client-upload reachability defect and proves the local signed-policy/checksum path without weakening either boundary. The pinned LocalStack runtime still lacks the required restart-data persistence evidence, so this fix does not satisfy the persistent object-store gate or justify starting E1.

## 2026-10-11 — D6 Tencent COS S3-compatibility candidate audit (rejected)

- With explicit user authorization, an isolated probe used the existing MiniShop COS identity only as a temporary runtime configuration. Its values were not copied into source, Compose, or logs. The probe never listed, read, or modified an existing MiniShop object; it used random `agent-d6-probe/` keys only.
- The first project-shaped probe failed honestly: the current upload module creates a default/path-style boto3 client, while the MiniShop COS client explicitly uses S3v4 virtual-hosted addressing. COS returned `403 PathStyleDomainForbidden` for the default generated POST and denied the corresponding default `HeadBucket`; no valid object was accepted through that path.
- A one-variable diagnostic using the MiniShop client's S3v4 virtual-hosted addressing made `HeadBucket` succeed, generated a valid pre-signed POST accepted with `201`, and accepted the exact known-key delete request. Its oversize form was rejected with `400 EntityTooLarge`, so COS does enforce the signed exact-length policy under the compatible addressing mode.
- The required integrity test still failed: after a valid checksum-bearing upload, `HeadObject(ChecksumMode=ENABLED)` returned the matching content length but no `ChecksumSHA256`. The two known temporary-key delete requests were accepted. No application source or persistent Agent configuration was changed, and scan -> parse -> frozen-attachment or restart recovery was intentionally not run after this hard-contract failure.

### Automatic audit decision

- **The Tencent COS investigation is approved and the Tencent COS replacement is rejected. D6 remains not approved and no later phase may start.** Addressing-style support would fix only the initial `403`; it cannot make the backend return the project's non-negotiable SHA-256 metadata. Do not weaken `S3DirectUploadStorage.inspect_quarantine_object(...)`, substitute size for checksum verification, or reuse the MiniShop bucket/identity as the Agent's permanent store merely because its POST path works.

## 2026-10-11 — D6 external S3 configuration injection (not approved)

- The user created an isolated AWS account, S3 bucket, and least-privilege IAM identity, but no cloud value has been copied into this workspace or output. Before this slice, every API/Worker/Beat service inherited hard-coded LocalStack object-storage values from the shared Compose environment; `backend/.env` alone could not override them.
- The shared six object-storage environment entries now use Docker Compose defaults. A Git-ignored root `.env` or the process environment can provide an external endpoint, public endpoint, region, bucket, access-key ID, and secret; when absent, the exact LocalStack defaults remain. This is the smallest switch that preserves the normal local stack while allowing an isolated cloud proof.
- `docker compose config --quiet` passed with no override. With harmless synthetic external values, rendered Compose output showed every object-storage field propagated to each service using the shared environment. An initial PowerShell regex assertion falsely reported them missing; direct inspection of those rendered non-sensitive lines confirmed propagation, so the assertion failure is retained as harness-only diagnostic evidence rather than an application failure. `verify-stack.ps1` then passed with PostgreSQL, Redis, LocalStack, migration head, API, and both Celery nodes healthy.

### Automatic audit decision

- **The external configuration-injection slice is approved; D6 remains not approved and no later phase may start.** The repository can now select an external S3-compatible backend without committing credentials or breaking the LocalStack default. No real AWS configuration, browser upload, checksum inspection, scan -> parse consumption, or restart persistence proof has run yet; those require the user to place the newly created IAM values in the local ignored root `.env`.

## 2026-10-11 — D6 AWS credential preflight (blocked; no object write)

- The Git-ignored root `.env` now contains all six required object-storage settings. A non-disclosing format check passed: both endpoints are AWS S3-shaped and equal, the region and bucket formats are valid, both credential fields are present with plausible lengths, and no quoted value was detected. No configuration value was printed or committed.
- `docker compose config --quiet` passed. A one-off API container therefore received the same Compose environment that the long-running API and Workers will receive. The initial read-only probe had a harness-only type error because it passed Pydantic `SecretStr` wrappers directly to boto3; source inspection showed the production storage module correctly calls `get_secret_value()`. Re-running the probe with that exact credential contract made no application or cloud mutation.
- AWS then rejected `HeadBucket` with `403`, and two independent bucket-level, read-only calls (`GetBucketLocation`, `ListObjectsV2(MaxKeys=1)`) each returned `InvalidAccessKeyId`. This is credential identity failure, not evidence of a missing S3 object permission or a project code defect. No object was created, listed, read, or deleted.

### Automatic audit decision

- **The AWS configuration-injection slice remains approved, but the real AWS object-store gate is blocked before its first write. D6 remains not approved and no later phase may start.** Replace or correct the local IAM access-key pair, then rerun identity and bucket preflight before authorizing the five-part upload/checksum/processing/restart proof. Do not grant `AmazonS3FullAccess` in response to this failure: `InvalidAccessKeyId` must be resolved at the IAM access-key identity boundary first.

## 2026-10-11 — D6 native AWS S3 persistent-object-store proof (approved; D6 not approved)

- After the user rotated the local IAM access-key pair, a one-off API container passed `HeadBucket`, `GetBucketLocation`, and `ListObjectsV2(MaxKeys=1)` against the configured AWS bucket; its configured region matched the bucket region. The long-running API, Worker, Beat, and report Worker were then recreated so the same Compose configuration became their runtime environment. No credential, endpoint, bucket name, or signed form was printed or committed.
- A real host-to-AWS probe used an API-container-generated pre-signed POST and a fresh `agent-d6-probe/<uuid>/` prefix. The exact fixture upload received HTTP `201`; the same payload against a form signed for one byte less received HTTP `400`. The API's normal `S3DirectUploadStorage.inspect_quarantine_object(...)` verified exact byte size and the SHA-256 returned by `HeadObject(ChecksumMode=ENABLED)`. API and Worker were recreated while the valid object remained, and the same inspection succeeded after restart. The two exact probe keys were then deleted successfully; no bucket-wide cleanup was performed.
- The real opt-in S3 integration chain ran from the host development environment with the AWS values supplied only as temporary process environment: it passed `2 passed, 1 warning` for direct upload -> checksum acceptance -> deterministic scan -> parsing -> frozen attachment context consumption, plus signed exact-length policy rejection. Random test object prefixes are removed by the test's exact-prefix cleanup. The warning is the existing Starlette `TestClient` deprecation warning.
- External S3 exposed a readiness defect that LocalStack hid: `check_object_storage()` used a hard-coded 0.5-second connect/read timeout with no retry. The same resident API credentials could pass a normal `HeadBucket` while `/health/ready` intermittently returned `object_storage: unavailable`. The health timeout is now a bounded setting (default 3 seconds, maximum 10) and is used for both boto3 timeouts; it remains a single fail-closed readiness probe. The external-S3 E2E test now accepts an explicitly supplied region while retaining `us-east-1` as its LocalStack default.
- Verification after rebuilding API/Worker: native AWS S3 E2E `2 passed, 1 warning`; selected direct-upload/settings/health tests `14 passed, 1 warning`; Ruff check and format passed; Compose validation passed; standard stack verification passed with `/health/ready` reporting object storage available; queue inspection found `celery=0`, `reports=0`, no active/reserved/scheduled tasks, zero durable in-flight tasks, and zero overdue broker-accepted events; `git diff --check` passed. The application code and test changes are limited to external-S3 configuration/testability and health-check timeout behavior.

### Automatic audit decision

- **The native AWS S3 persistent-object-store gate is approved. D6 remains not approved and no later phase may start.** This closes the required pre-signed policy, checksum, scan/parse/frozen-consumption, and application-restart retention evidence without weakening the S3 SHA-256 contract. It does not prove a customer-facing browser CORS flow, AWS-account backup/restore, bucket lifecycle/retention policy, normal-volume low-watermark admission, customer-load capacity/SLO, or the other independent D6 requirements; those remain explicit D6 gaps.

## 2026-10-11 — D6 normal PostgreSQL-volume low-watermark admission (approved; D6 not approved)

- The prior boundary audit required an authenticated, backend-specific capacity signal rather than a guessed free-space threshold in the API process. Compose now runs an internal-only `capacity-signal` process as UID `10001`, mounting only the normal `postgres_data` volume at `/var/lib/postgresql/data:ro`. Its authenticated `GET /v1/postgres-volume` response is versioned (`capacity-signal/v1`), bounded, non-cacheable, and contains only an observation timestamp plus available/total bytes. Docker inspection verified that mount as `rw=false`; the signal is not exposed on a host port.
- `create_task(...)` now calls the capacity admission contract before acquiring either PostgreSQL advisory lock or inserting a task. When enabled, malformed, stale, unauthenticated, oversized, unreachable, or otherwise invalid signals become a typed `TaskCapacitySignalUnavailableError`; a valid signal below the configured watermark becomes `TaskCapacityLowWatermarkError`. Both paths are fail-closed and the conversation API returns a generic `503` with `Retry-After`, without exposing signal or token details. The existing count-based global/company limits remain unchanged and are a separate control.
- Readiness now reports `task_capacity` and returns `503` if enabled capacity admission cannot accept a new task. Production settings also reject the Compose development token. The standard `verify-stack.ps1` now verifies both sidecar liveness and API-side capacity admission, so a stack cannot be declared ready while the only admission signal is unavailable.
- Verification: focused unit/integration/settings selection passed `36 passed, 1 warning`; the warning is the existing Starlette `TestClient` deprecation warning. Ruff check and format passed for every changed capacity/readiness source and focused test. `docker compose config --quiet`, API rebuild, and the extended standard stack verification all passed. Against the resident Compose service, an authenticated API-side probe accepted a schema-valid live volume signal; an unauthenticated request received `403`; separate transient API containers proved both an artificially high low-watermark rejection and an unreachable-signal rejection. These probes did not create tasks, call a model, write to AWS S3, or expose credentials.

### Automatic audit decision

- **The normal PostgreSQL-volume low-watermark admission slice is approved; D6 remains not approved and no later phase may start.** It proves a real normal-volume signal, read-only sidecar boundary, fail-closed admission, readiness propagation, and deterministic error contracts. It is not a customer-load capacity/SLO claim, a disk-full application-recovery proof, a browser-object-storage capacity contract, or a full HTTP request under a physically exhausted normal PostgreSQL volume. Persistent AWS object storage is already proven separately, but its account-level capacity/lifecycle/backup policy and the other listed D6 fault boundaries remain unproved.

## 2026-10-11 — D6 AWS bucket governance baseline audit (not approved)

- A resident API-container probe made only bucket-configuration reads; it did not list, read, write, or delete objects and did not disclose any bucket, endpoint, or credential value. The configured AWS bucket reports versioning enabled, a configured public-access block, and configured default encryption.
- The bucket has no lifecycle configuration. `GetObjectLockConfiguration` returned AWS's `ObjectLockConfigurationNotFoundError`, which means Object Lock is not configured; it is not an IAM denial. This application has no source-controlled retention/lifecycle policy to compare or enforce against that external state.

### Automatic audit decision

- **The AWS bucket governance baseline audit is complete but not approved as a retention/backup gate; D6 remains not approved and no later phase may start.** Versioning, public blocking, and default encryption are useful controls, but they do not choose an evidence-retention period, noncurrent-version expiry, incomplete multipart cleanup, legal-hold/Object-Lock requirement, backup/restore responsibility, or cost ceiling. Applying a lifecycle rule would be a meaningful external data-retention and billing decision, so it requires an explicit user policy before any AWS mutation.

## 2026-10-11 — D6 real capacity-signal HTTP rejection chain (approved; D6 not approved)

- The prior normal-volume capacity slice had two separate proofs: direct resident-sidecar admission and an API transaction rollback regression with an injected error. A new opt-in E2E test joins them without mocking the capacity module: it uses the authenticated Compose `capacity-signal` service, sets only an intentionally impossible low-watermark in the test's settings snapshot, verifies that the real contract raises `TaskCapacityLowWatermarkError`, then submits the normal conversation-message HTTP request.
- The test ran in an automatically removed Compose container with the test directory mounted read-only. Its database fixture wraps every write in a transaction rollback. The actual HTTP response was `503` with the configured `Retry-After`; the test asserted zero `AnalysisTask`, zero `AnalysisTaskOutboxEvent`, and zero `ConversationMessage` rows after rejection. It did not call a model, publish a broker event, modify the resident application database, or access AWS S3.
- Verification: host regression selection passed `13 passed, 1 skipped, 1 warning` with the real-dependency test intentionally skipped outside the Compose network; the temporary Compose test runner passed `1 passed` with `RUN_CAPACITY_SIGNAL_E2E=1`. Ruff check and format passed for the changed test. The two first runner attempts are retained as harness diagnostics: the production image intentionally excludes tests, and the root-directory Ruff path omitted the `backend/` prefix; neither reached the application request path or changed persistent state.

### Automatic audit decision

- **The real capacity-signal HTTP rejection-chain slice is approved; D6 remains not approved and no later phase may start.** It proves real sidecar -> capacity contract -> API error mapping -> transaction rollback on the same Compose network. It does not prove a physical low-free-space condition in the normal persistent PostgreSQL volume, successful-task capacity/SLO, or external object-store lifecycle/backup policy.

## 2026-10-11 — D6 capacity-signal timeout configuration bound (approved; D6 not approved)

- Capacity admission is on the synchronous task-creation path. Although its default timeout was one second, the setting previously had only the generic positive-integer validation; a future environment value could make every new-task request wait for an arbitrarily slow or unreachable signal.
- `MAX_CAPACITY_SIGNAL_TIMEOUT_SECONDS` now fixes the upper bound at five seconds. The existing default remains one second, and startup rejects zero, negative, or greater-than-five values before any service begins admitting work. Five seconds is an explicit worst-case availability tradeoff, not a measured customer latency target.
- Verification: focused settings/capacity/readiness regression passed `19 passed, 1 warning`; the warning is the existing Starlette `TestClient` deprecation warning. Ruff check and format passed for every changed source/test file. Compose configuration, API rebuild, the extended standard stack verification, and an API-container assertion that the resident timeout is within the fixed bound all passed. No task, model call, AWS object operation, or database data mutation occurred.

### Automatic audit decision

- **The capacity-signal timeout-bound slice is approved; D6 remains not approved and no later phase may start.** It prevents a configuration-drift availability regression in the new admission path. It does not establish a capacity/SLO limit, a physical normal-volume exhaustion response, or AWS lifecycle/backup policy.

## 2026-10-11 — D6 capacity-signal response-integrity contract (approved; D6 not approved)

- The original shared token authenticated requests to the sidecar but did not authenticate a response before the API used its capacity values. The sidecar now computes an HMAC-SHA256 over the exact JSON response body and returns it only for the capacity endpoint; the API verifies that header before JSON parsing and turns a missing or mismatched signature into the existing fail-closed unavailable-signal result.
- Unit coverage proves an otherwise schema-valid but unsigned response is rejected. The sidecar helper coverage proves the signature is derived from the exact body bytes, rather than an independently reconstructed payload. A rebuilt resident API successfully consumed a signed response from the rebuilt resident sidecar through the normal `require_task_capacity(...)` contract.
- Verification: focused capacity/admission/conversation/readiness selection passed `30 passed, 1 skipped, 1 warning`; the skip is the explicitly opt-in Compose E2E and the warning is the existing Starlette `TestClient` deprecation warning. Ruff check/format, Compose validation, rebuild, standard stack verification, and the resident signed-signal probe all passed. No task, model call, AWS object operation, or durable application-data mutation occurred.

### Automatic audit decision

- **The capacity-signal response-integrity slice is approved; D6 remains not approved and no later phase may start.** It closes the client-authentication-only gap for the bounded internal signal protocol. It is HMAC over the internal Compose network, not a claim of mTLS or protection against a host/Docker administrator who can already read the shared secret. Capacity/SLO, physical normal-volume exhaustion, and AWS lifecycle/backup-policy gates remain unproved.

## 2026-10-11 — D6 connection-pool tenant-variable reuse regression (approved; D6 not approved)

- `set_tenant_scope(...)` stores the company only on the owning SQLAlchemy `Session` and writes PostgreSQL `app.company_id` with transaction-local `set_config(..., true)`. The existing RLS regression proved scoped reads but did not prove cleanup after a physical connection returned to a pool.
- A new migrated-test-PostgreSQL regression constructs a separate one-connection pool, records `pg_backend_pid()`, assigns tenant `987654321`, commits and closes that Session, then creates a fresh unscoped Session. It proves the same backend PID is reused and `current_setting('app.company_id', true)` is empty on the fresh Session. This is a pool-reuse boundary proof, not a claim that deferred E1 application authorization/RLS validation is complete.
- Verification: `pytest tests/integration/documents/test_tenant_vector_rls.py -q` passed `2 passed, 1 warning`; focused Ruff check and format check passed. The warning is the existing Starlette `TestClient` deprecation warning.

### Automatic audit decision

- **The connection-pool tenant-variable slice is approved; D6 remains not approved and no later phase may start.** It directly covers P6-4's no-reused-tenant-variable condition without broadening its scope into E1.

## 2026-10-11 — D6 resident Redis interruption/readiness recovery (approved; D6 not approved)

- With Broker queues empty and no active, reserved, scheduled, or durable in-flight task, the resident Compose `redis` service was stopped. The resident API returned `HTTP 503` from `/health/ready` with `database: ok`, `redis: unavailable`, and later dependency states `unknown`; it did not report readiness during the interruption.
- Redis was immediately restarted, reached Docker health `healthy`, and the standard stack verification then passed PostgreSQL, Redis, the configured object-storage bucket, migration head, and both Celery pings. Queue inspection again found `celery=0`, `reports=0`, no active/reserved/scheduled work, and zero durable in-flight tasks.

### Automatic audit decision

- **The resident Redis interruption/readiness-recovery slice is approved; D6 remains not approved and no later phase may start.** It proves this dependency interruption blocks readiness and returns to a verified empty state after recovery. It does not prove in-flight Redis message recovery or replace the separate PostgreSQL/object-storage interruption evidence.

## 2026-10-11 — D6 scope correction: AWS lifecycle is not a P6-4 prerequisite

- The earlier AWS governance audit remains valid: the bucket lifecycle and Object Lock policies are absent and require explicit user retention, legal-hold, backup, and billing decisions before mutation. Those controls belong to final E6/P8 data-retention and production-governance scope.
- Re-reading the authoritative P6-4 exit contract confirms that D6 requires reproducible rebuild, dependency/readiness, secrets/configuration, queue backpressure, disk/clock/pool boundaries, and measured low concurrency. It does not make an account-level lifecycle or Object Lock policy a D6 precondition. The native AWS S3 restart-retention and upload-to-consumption contract remains the relevant D6 object-store evidence.

### Automatic audit decision

- **This corrects the D6 evidence scope only.** It neither approves AWS retention governance nor weakens it; it removes an incorrect D6-to-E6 dependency so the remaining D6 audit can be based on the actual P6-4 contract.

## 2026-10-11 — D6 resident PostgreSQL interruption/readiness recovery (approved; D6 not approved)

- With no Broker backlog, active/reserved/scheduled Worker work, or durable in-flight task, the resident Compose `postgres` service was stopped. The resident API returned `HTTP 503` with only the generic contract `service_unavailable` / `database unavailable`; it neither returned ready nor exposed driver, host, credential, or SQL details.
- PostgreSQL was immediately restarted and reached Docker health `healthy`. The standard stack verification then passed PostgreSQL readiness, Redis, configured object-storage bucket access, migration head, and both Celery pings. Queue inspection again found `celery=0`, `reports=0`, no active/reserved/scheduled work, and zero durable in-flight tasks.

### Automatic audit decision

- **The resident PostgreSQL interruption/readiness-recovery slice is approved; D6 remains not approved and no later phase may start.** It proves the public readiness boundary safely stops during a real database outage and recovers cleanly while idle. It does not replace the separate bounded-volume database-full recovery or in-flight execution recovery evidence.

## 2026-10-11 — D6 resident object-storage interruption/readiness recovery (approved; D6 not approved)

- AWS S3 itself was not stopped. Instead, the resident API alone was recreated with a temporary loopback-unreachable object-storage endpoint while retaining the ordinary database, Redis, Worker, and bucket configuration. The real storage health path attempted its bounded S3 client operation and `/health/ready` returned `HTTP 503` with `database: ok`, `redis: ok`, and `object_storage: unavailable`. No object operation was requested and no S3 credential, endpoint, or bucket value was emitted.
- The API was immediately recreated using the original ignored runtime configuration. Standard stack verification then passed PostgreSQL, Redis, configured object storage, migration head, and both Worker pings; queue inspection found `celery=0`, `reports=0`, no active/reserved/scheduled work, and zero durable in-flight tasks.

### Automatic audit decision

- **The resident object-storage interruption/readiness-recovery slice is approved; D6 remains not approved and no later phase may start.** It proves a real client connectivity failure blocks readiness and can recover with the normal configuration. It does not simulate an AWS regional outage, prove browser CORS, or replace the separately recorded AWS restart-retention and capacity contracts.

## 2026-10-11 — D6 / P6-4 final automatic gate audit (approved for its stated local scope)

| P6-4 exit requirement | Current evidence | Gate result |
|---|---|---|
| Clean rebuild; dependencies, migrations and readiness reproducible | Clean Compose rebuild and bucket-init recovery are recorded above; after the current Redis, PostgreSQL and object-storage drills, `verify-stack.ps1` again passed database, Redis, configured bucket, migration head and both Worker pings. | passed |
| Configuration and secrets boundary | Object-storage configuration is injected only through ignored runtime environment; production rejects the Compose development capacity token; no credentials were printed or committed in the AWS proof. | passed for local runtime configuration, not credential-rotation governance |
| Queue backpressure and safe admission | Existing global/company limits plus authenticated, freshness-bounded, HMAC-protected PostgreSQL-volume capacity admission reject before locks or task writes; real HTTP rejection proved no task, Outbox or message insertion. | passed |
| Disk boundary and recovery | Isolated named-volume real Worker/PostgreSQL ENOSPC proves no false terminal state before capacity recovery, then lease recovery; normal PostgreSQL-volume low-watermark admission fails closed. Application ENOSPC is non-retryable. AWS S3 upload/policy/checksum/scan/parse/frozen-consumption survives API/Worker recreation. | passed for the tested bounded local and AWS paths; no customer-data durability or SLO claim |
| Clock and long-call boundary | Process-only `libfaketime` drill proves claims/leases use PostgreSQL time; real loopback slow-provider timeout, independent heartbeat, late-result fencing and heartbeat-database-failure recovery prove the stated bounded behavior. | passed for tested paths |
| No pooled Session/tenant-variable reuse, result crossing or budget oversell | The new one-connection-pool regression proves a fresh Session on the same PostgreSQL PID has no prior `app.company_id`. Existing execution/admission, fencing, model-ledger and concurrency regressions cover the remaining task/result/budget boundaries; the current D6 regression selection passed `73 passed, 1 warning`. | passed for P6-4; it is not the deferred E1 authorization/RLS completion claim |
| Low-concurrency measurement and candidate control | The pre-frozen read-only `business_db` workload has valid concurrency-1 and concurrency-2 samples with memory, task/queue P95, timeout/cost state and queue observations. Concurrency 2 worsened task P95 and memory, so Worker concurrency 1/prefetch 1 remains the only adopted baseline. | passed; no SLO or capacity claim beyond this workload |
| DB, Redis and object-store interruption safe stop/recovery | Resident Redis interruption returned explicit readiness `503 redis: unavailable`; resident PostgreSQL returned generic `503 database unavailable`; a resident API with a loopback-unreachable object-store endpoint returned `503 object_storage: unavailable`. Each was restored and followed by passing stack verification and empty queues. | passed for idle dependency interruption |

- Fresh verification for this gate: `pytest tests/modules/workflow/test_capacity.py tests/modules/observability/test_health_repository.py tests/integration/observability/test_health.py tests/integration/documents/test_tenant_vector_rls.py tests/modules/workflow/test_task_execution_service.py tests/modules/runtime/test_model_governance.py tests/modules/runtime/test_model_settlement_integration.py tests/integration/workflow/test_tasks.py -q` passed `73 passed, 1 warning`; focused Ruff check/format passed. The warning is the existing Starlette `TestClient` deprecation warning. The post-drill standard stack verification and queue inspection both passed.

### Automatic audit decision

- **D6 / P6-4 is approved for the explicitly tested local single-node scope. The next phase may proceed.** This supersedes only earlier D6 “not approved” statements whose listed gaps are now closed by later evidence. It does not claim E1 application authorization/RLS completion, AWS lifecycle/Object Lock or backup governance, browser CORS, a customer-load SLO, multi-node availability, provider-side cancellation, or any capacity beyond the measured concurrency-1 local workload.

## 2026-10-11 — P5-1 MCP evidence-read pre-implementation audit (not approved)

- Current source has no MCP Server, MCP Client, or `evidence_read` tool. The existing business capability is local `rag_search`: `workflow/nodes.py` constructs `RAGTool`, and `ToolRuntime` performs frozen company/document scope validation, current membership/document visibility checks, budget reservation, redacted events, and `ToolCallRecord` persistence before the local tool executes.
- Therefore an MCP adapter must preserve, rather than bypass, the existing call chain: `Workflow -> ToolRuntime -> MCP Client -> trusted local MCP Server -> evidence-read implementation`. The server has no authority to publish, authorize, or expand a document/company scope. The client-facing catalog will expose only the namespaced `agent-evidence:evidence_read` capability, with one bounded request shape and structured success/error output; no resources, prompts, links, `input_required`, or side-effecting tools are enabled in this first slice.
- The Python MCP SDK was installed only in the development virtual environment for API verification. The actual installed SDK is `mcp 2.3.0` and exposes `MCPServer` and `Client`; it is not the older `FastMCP` API. Official MCP guidance also requires STDIO servers not to write logs to stdout. The repository dependency lock/change and implementation have intentionally not begun until this contract audit is complete.

### Automatic audit decision

- **P5-1 is not approved.** The next implementation slice must add the SDK as a bounded runtime dependency, a local STDIO server/client adapter, explicit protocol/version/catalog constraints, Runtime-mediated authorization and audit preservation, plus local/MCP equivalence and failure tests. It must not expose a database connection as an MCP capability or present local-transport evidence as remote authentication.

## 2026-10-11 — P5-1 local MCP evidence-read implementation slice (not approved)

- Added the bounded Python SDK dependency `mcp>=2.3,<3.0`, a local `agent-evidence` MCP Server at protocol version `1.0.0`, and its only catalog entry `evidence_read`. It delegates to the existing read-only `RAGTool`; the server owns no publication, authorization, or scope-expansion decision. STDIO entry code intentionally has no stdout logging.
- `McpEvidenceReadTool` keeps the existing local Agent-facing name `rag_search`, so workflow code continues to call `ToolRuntime` before the transport. Its client verifies that the server catalog is exactly `[evidence_read]`, converts malformed/error output to bounded tool failures, and defaults to a 15-second SDK read timeout. `KNOWLEDGE_EVIDENCE_TRANSPORT=local` remains the default; explicit `mcp_stdio` is a reversible local-transport candidate.
- Verification: in-process MCP `tools/list -> tools/call` preserved a deterministic local reader result; a real child STDIO server exposed only `evidence_read`; catalog-drift and reader-failure cases returned controlled errors; and a revoked membership was rejected by `ToolRuntime` before the MCP server reader was called. Focused MCP/RAG/Runtime/settings regression passed `43 passed`; Ruff check and changed-file format checks passed.
- A real STDIO read request against the resident local RAG implementation exceeded the first 30-second observation window during local embedding execution. It produced no result and left no persistent change; all four short-lived probe processes exited before a later cleanup command. This is not valid `tools/call` success evidence. The new SDK timeout bounds future attempts, but an actual normal STDIO evidence-read result still must be proven.

### Automatic audit decision

- **P5-1 remains not approved.** The adapter contract, default rollback, catalog constraint and Runtime-mediated denial are implemented and tested, but the required real STDIO `tools/list -> tools/call` evidence-read success/equivalence remains unproved. Do not claim remote MCP authentication, external-server trust, or model-visible MCP-loop integration from this local slice.

## 2026-10-11 — P5-1 STDIO evidence-read cold-start correction (not approved)

- The first real STDIO `evidence_read` request loaded the local embedding model in its newly spawned child process. A 15-second SDK read limit therefore converted a valid cold start into `mcp_transport_unavailable`; all probe processes exited without persistent business change. This was a transport-candidate configuration error, not a server success result.
- The bounded local cold-start budget is now 30 seconds. Under that bound, the same real STDIO flow completed `tools/list -> tools/call` in `19.8 seconds` and returned the valid read-only `insufficient_evidence` result for the explicitly empty document scope. It made no model-provider call and no business-database write. The server's framework logging was forwarded on stderr; no JSON-RPC stdout corruption was observed.

### Automatic audit decision

- **P5-1 remains not approved.** Real local STDIO catalog and normal-call evidence now exists, but it is a cold-start cost observation rather than an SLO. The next slice must cover disconnected transport, malformed response, and `input_required`/unapproved extension handling; then run an authorized non-empty scope local/MCP equivalence proof. Remote MCP authentication and deployment remain explicitly out of scope.

## 2026-10-11 — P5-1 MCP protocol-failure completion slice (not approved)

- The adapter now explicitly rejects any MCP `result_type` other than `complete`. In particular, a protocol-level `input_required` response is returned as `mcp_input_required_not_supported`; it cannot silently become a successful evidence result or cause the Agent to solicit unapproved input.
- New SDK-backed regressions prove: an immediately exiting STDIO child becomes the repairable `mcp_transport_unavailable` result; a changed catalog becomes `mcp_catalog_mismatch`; a non-JSON tool response becomes `mcp_evidence_read_malformed`; and `input_required` is refused as above. Existing Runtime regression still proves revoked membership blocks the MCP reader before its first call.
- Verification: MCP adapter, Runtime, local RAG and settings selection passed `46 passed`; Ruff check and changed-file format checks passed. The known unrelated formatting drift in `workflow/nodes.py` was not rewritten.

### Automatic audit decision

- **P5-1 remains not approved.** Normal STDIO empty-scope execution and protocol failures are now evidenced. The remaining required proof is one non-empty, currently authorized document scope whose real local read and real STDIO MCP read have equivalent bounded evidence semantics. Do not treat a synthetic reader or an empty-scope insufficiency response as that business-equivalence proof.

## 2026-10-11 — P5-1 controlled local MCP evidence-read final gate (approved for stated local scope)

- `McpEvidenceReadTool` now invokes a local STDIO `agent-evidence` server through the existing `ToolRuntime`; the Agent-facing name remains `rag_search`. The server exposes exactly one `evidence_read` capability and delegates only to the existing read-only `RAGTool`. Authorization, frozen company/document scope, current membership/document visibility, budget reservation and durable redacted tool audit all remain before the transport.
- The original candidate supplied an explicit minimal RAG configuration allowlist, but it still transmitted the business-read password solely to satisfy global Settings validation. That was not a valid least-privilege conclusion and is superseded by the correction entry below.
- Fresh Worker-image verification discovered that unpinned `transformers` resolved to `5.19.0`, which cannot import with this CPU-only `torch 2.6.0` image. A disposable image test proved `sentence-transformers 5.7.0 + torch 2.6.0+cpu + transformers 5.14.1` imports and produces a real 384-dimensional vector, so `requirements-ml.txt` now pins `transformers==5.14.1`. A rebuilt Worker ran that exact version and produced the same real vector shape.
- In a short-lived, fully cleaned local probe, a newly created approved member, completed document, one 384-dimensional document chunk and frozen task scope were passed through `ToolRuntime` twice: once to local `RAGTool`, once to the real STDIO MCP client/server path. Both calls succeeded with `status=ready`, the same one-element `allowed_chunk_ids`, and the same one-element evidence chunk-ID set. The temporary task, document, membership, company and user were deleted in a separate cleanup transaction; a direct post-check found zero probe companies and users.
- Fresh verification: `pytest tests/modules/knowledge/test_mcp_adapter.py tests/modules/runtime/test_tool_runtime.py tests/modules/analysis/test_tools.py tests/modules/system/test_settings.py -q` passed `47 passed`; focused Ruff and format checks passed; `git diff --check` had no errors (only existing CRLF warnings); rebuilt Worker plus `verify-stack.ps1` passed PostgreSQL, Redis, configured object storage, migration head and both Celery pings; queue inspection found no queued, active, reserved, scheduled or durable in-flight work.

### Automatic audit decision

- **P5-1 is approved for the explicitly tested local single-node STDIO scope.** It proves controlled local catalog/transport behavior, Runtime-mediated authorization preservation, protocol-failure normalization and real non-empty local/MCP evidence equivalence. It does not prove remote MCP authentication or authorization, external-server trust, network deployment, model/transport cold-start SLOs, or customer-load behavior. The first Worker-local model cache download remains an environment-startup cost; it is not counted as a request SLO.

## 2026-10-12 — P5-1 gate correction after contract re-audit (not approved)

- The preceding P5-1 approval is withdrawn. The real local STDIO equivalence probe and the focused regression result remain useful evidence, but they did not satisfy all requirements in the authoritative P5-1 contract.
- Missing or invalid at the prior gate: Runtime did not transmit a per-request client metadata and authorization-context binding; the MCP client checked only a tool name, not the fixed request Schema; the exact same illegal input had not been shown rejected by both local and MCP paths; resource-link rejection was only incidental rather than directly tested; and the child inherited a real business-read password that RAG did not need.
- The candidate is now being corrected with an exact SDK pin, fixed STDIO and tool-contract identifiers, no catalog cache, Runtime-injected request context containing task/execution/actor/auth-version/role/company/document-scope fingerprint, server-side shape-and-scope validation, and a response receipt that the client verifies. The child receives a non-credential business-password sentinel only to satisfy the application-wide Settings validator, so accidental future business-DB use fails instead of inheriting the real secret.

### Automatic audit decision

- **P5-1 is not approved.** No subsequent phase may use the withdrawn approval. The next gate must rerun focused regressions and a real authorized non-empty local-versus-STDIO request using the corrected Worker image, then audit the exact P5-1 checklist including malformed result, resource link, input-required, disconnect, catalog drift, current authorization, and scope equality. This remains a controlled local-transport scope and cannot establish remote MCP authentication or deployment.

## 2026-10-12 — P5-1 corrected local MCP final gate (approved for stated local scope)

- The corrected adapter pins the runtime dependency to `mcp==2.3.0`, checks that installed SDK version before opening a client, fixes the `stdio` transport and `evidence_read/v1` contract identifiers, and accepts only one catalog entry with the exact bounded input Schema. It refreshes `tools/list` for every call; there is intentionally no directory cache, so no cached catalog can cross authorization subjects, scopes, or protocol versions.
- `ToolRuntime` injects a fresh request-only context only after current user, role, company and frozen-document authorization have passed. The context binds the task ID, execution ID, actor ID/auth version, authorized role, company ID and document-scope SHA-256. The trusted local server validates its shape and scope relation, sends only the original RAG request to the existing reader, and returns a context receipt; the client rejects a missing or mismatched receipt. The server never uses this metadata to grant authorization. The child no longer receives the real business-read password; its Settings-required value is a non-credential sentinel.
- Focused regressions now cover normal local result preservation, reader failure, exact catalog/Schema drift, malformed result, explicit resource-link result, `input_required`, disconnected STDIO, missing context, mismatched context receipt, the explicit environment allowlist, current revoked membership, and the same out-of-scope document input rejected before either local or MCP reader executes. `pytest tests/modules/knowledge/test_mcp_adapter.py tests/modules/runtime/test_tool_runtime.py tests/modules/analysis/test_tools.py tests/modules/system/test_settings.py -q` passed `51 passed`; adapter/test Ruff checks and all four changed-file format checks passed. The existing broad `except Exception` in `ToolRuntime` is not part of this slice and was not rewritten.
- The rebuilt real Worker reported installed SDK `2.3.0`, contract `evidence_read/v1`, and transport `stdio`. A disposable approved user/company/document/384-dimensional chunk/frozen task was executed through `ToolRuntime` with both local `RAGTool` and a real STDIO child. Both returned `success=true`, `status=ready`, the same one-element `allowed_chunk_ids`, and the same one-element evidence chunk-ID set; successful MCP completion also implies the server receipt matched the injected context. The first cleanup ordering was invalid because the task still referenced its document; a targeted follow-up cleanup used the correct `task -> document -> company/user` order and verified probe companies/users were both zero. No probe data remains.
- Standard stack verification after the rebuilt Worker passed PostgreSQL, Redis, configured object storage, migration head and both Celery pings. Queue inspection found `celery=0`, `reports=0`, no active/reserved/scheduled work, and zero durable in-flight tasks. The child performed unauthenticated Hugging Face model metadata/cache access during cold startup; this is an observed local environment dependency/cold-start cost, not an MCP request SLO.

### Automatic audit decision

- **P5-1 is approved for the explicitly tested local single-node STDIO scope.** This supersedes the withdrawn P5-1 approval only after the corrections and fresh evidence above. It proves one existing evidence-read capability preserves Runtime control and bounded protocol behavior across the local/MCP transport. It does **not** prove remote MCP authentication or authorization, external-server trust, HTTP/network deployment, model cache availability, cold-start or customer-load SLOs, remote egress governance, or independent least-privilege database credentials for a separately deployed MCP service.

## 2026-10-12 — P5-2 model/tool trace and audit pre-implementation audit (not approved)

- Current source already provides useful partial evidence: `ModelCallRecord` has a durable unique `model_call_id`, task/attempt/node linkage, frozen pricing fields, `reserved`/`settled`/`unknown` billing state and privacy-safe prompt identifiers; `reserve_model_call` commits its reservation before a provider request, and `record_model_call` retains timeout/failure cost uncertainty instead of treating it as free. Existing focused and integration tests cover reservation, settlement, duplicate settlement avoidance and a Worker timeout retained as `unknown`.
- This is not the full P5-2 contract. `ToolCallRecord` has no independent `tool_call_id`, no originating `model_call_id` or provider-call identifier, and no durable mapping from a model instruction to the tool result fed back to that model. The present `ToolRuntime` records tool start/completion by task/attempt only. It therefore cannot prove a report's evidence/tool result originated from the exact model decision that requested it, nor safely distinguish resumed or provider-switched calls.
- No ordinary telemetry pipeline, bounded buffer/overflow policy, or failure-injection proof exists. Durable workflow audit writes are committed before current read-tool execution, which is useful for the existing controlled readers, but it is not a demonstrated general fail-closed rule for future sensitive actions or a substitute for the P5-2 telemetry requirement.

### Automatic audit decision

- **P5-2 is not approved.** P5-1 remains approved only for its local MCP scope; no later P5/P7 promotion may use the partial ledger as complete model/tool traceability. The next slice must freeze an explicit model-call to tool-intent to tool-result contract, add only the necessary migration and Runtime propagation, and demonstrate audit-write failure before a sensitive action plus bounded non-critical telemetry behavior. It must not manufacture a model/tool association for the current non-native tool loop.

## 2026-10-12 — P0-3 evaluation-cost-state pre-implementation audit (not approved)

- The automatic dependency re-audit found that P2 cannot honestly start: P0 remains unapproved, P1-2 has not frozen the framework-neutral `ModelRequest`/`ModelResponse`/tool-loop contracts, and the current Data/Knowledge agents call tools programmatically rather than from a model tool instruction. Adding an origin-model field to those calls would manufacture a trace.
- The current persisted-task observation instead has an immediate P0-3 measurement defect: it sums `ModelCallRecord.cost` without inspecting `billing_status`. A reserved/unknown provider call can therefore be represented as a numeric total (or can make observation parsing fail if its cost is null), even though `model_governance` deliberately records that its charge is unknown. `EvaluationObservation` and run metrics have no explicit total-cost status.
- This slice's only variable is evaluation cost representation. It will add a privacy-safe settled-cost aggregate and an explicit `passed`/`unknown` status derived from the durable model ledger, preserve zero cost only for a task with no model calls, and make artifacts display uncertainty. It will not alter pricing, model requests, task behavior, or start a paid E2E run.

### Automatic audit decision

- **P0-3 is not approved.** The next implementation must prove mixed settled/unknown ledger rows do not become a false total, an all-settled ledger does aggregate exactly, and zero-call rejection remains an explicit zero-cost observation. P2 and P5-2 remain blocked by their stated prerequisites.

## 2026-10-12 — P0-3 evaluation-cost-state implementation and automatic audit (slice approved; P0 not approved)

- `EvaluationObservation` now derives a privacy-safe `cost_status` from durable `ModelCallRecord.billing_status`: a task with no model calls is the explicitly known `0.000000`; a task whose calls are all `settled` exposes the six-decimal settled total; any reserved, unknown, or null-cost row exposes no total and records `unknown`. `EvaluationMetrics` carries the corresponding all-observation `settled_cost` and status. A model call is never re-priced or re-settled by evaluation.
- The persisted-observation regression has one all-settled two-call total (`0.030000`), one mixed settled/unknown ledger case that previously raised `Decimal('None')` and now returns `cost=null`, `cost_status=unknown`, and one zero-call terminal case. A run-level regression proves a mixed batch has no total. The evaluation CLI report explicitly renders the status; a container-local `--simulate-unavailable` run displayed `Settled model cost: unknown (status: unknown)`. That artifact is intentionally simulated and did not invoke a model, Worker or business database.
- The ordinary evaluation image had drifted from the current runtime dependency boundary: `backend/.dockerignore` omits tests (so verification mounts the source tree), while `requirements-evaluation.txt` duplicated an old subset and omitted runtime-required `boto3`/`botocore` and `mcp`. It now inherits `requirements.txt` and adds only test/lint dependencies. A freshly rebuilt evaluation image successfully imported all three packages. This is test-environment parity only; no production image or runtime behavior changed.
- Fresh verification: mounted-source evaluation suite `48 passed, 1 skipped`; focused cost/CLI regression `38 passed`; the new evaluation image imported `boto3`, `botocore`, and pinned `mcp 2.3.0`; `ruff check --ignore EXE002,TRY004` for the changed evaluation files passed; `git diff --check` passed. The unignored focused Ruff/format gate remains blocked by pre-existing executable-bit/no-shebang diagnostics, an old `TRY004` in `run_business_evaluation.py`, and older whole-file formatting drift in three dirty files; none points to this cost-state change, and no broad user-worktree reformat was applied.

### Automatic audit decision

- **The P0-3 cost-state and evaluation-image-parity slice is approved. P0 remains not approved.** This proves truthful aggregation of the existing durable model ledger and a runnable current evaluation test image. It does not provide a real 30-case task/rejection map, a current paid-model baseline, business-quality evidence, a provider cost settlement result, a clean whole-worktree lint gate, P1 contracts, or P2/P5-2 model-to-tool traceability. The next legal work is P0-2/P0-3 real persisted baseline preparation, not P1/P2.

## 2026-10-12 — P0-2 current persisted-baseline mapping pre-audit (not approved)

- The present platform database was read without mutation and contains zero `analysis_tasks`, companies, data sources, documents and users. The archived five-case baseline artifact names task IDs `125`–`129`, but those rows no longer exist, so it is historical failure evidence only and cannot be rerun, re-labelled, or promoted as the current baseline.
- A valid current run must create a disposable authorized evaluation tenant, a real ready data source and schema snapshot for the isolated demo business database, and the frozen generated business-document corpus. Analysis cases must enter through `POST /conversations -> POST /messages -> Outbox -> Worker`; each task must explicitly freeze only the document IDs matching its Gold scenario. The four Gold `security_rejection` cases must instead produce request-level rejection rows with zero task side effects; they are not model tasks and must not be fabricated as failed tasks.
- The existing fixture maps four document profiles (`sales_decline`, `quality_spike`, `margin_pressure`, `receivable_risk`) plus the metric reference and empty-scope cases to the generated corpus. A runner must persist the case ID, task or rejection correlation, frozen source/snapshot/corpus versions, model configuration, terminal time, model-ledger cost status and cleanup manifest without writing the Gold answer key into an Agent prompt.

### Automatic audit decision

- **P0-2 remains not approved.** No paid 30-case run has started. The next slice must first implement and test the disposable bootstrap/submission/mapping harness, then run a small current real-worker smoke before any development-set batch. The heldout seven cases remain frozen and may not be used to tune the harness, prompt or model configuration.

## 2026-10-12 — AWS S3 configuration revalidation (approved for the existing object-storage scope)

- The running API and Worker both reported a complete external AWS-shaped object-storage configuration without exposing endpoint, bucket, or credential values. An API-side `HeadBucket` check passed.
- The opt-in object-storage E2E suite was run against those live settings by passing them only within the short-lived evaluation container. It passed `2 passed in 12.43s`: direct presigned upload, checksum acceptance, deterministic scan, parse, ready-version frozen-context consumption, and rejection of a signed exact-length-policy violation.
- The E2E cleanup contract was tightened before the final run. It now places the random quarantine prefix in `finally` immediately after session creation, adds the random parsed prefix once a version exists, and asserts each exact prefix is empty after deletion. It does not list, alter, or delete any non-test prefix. The test database fixture rolls back its rows.
- Fresh static verification passed for the changed test, and `git diff --check` passed for it. `verify-stack.ps1` then passed PostgreSQL, Redis, configured object-storage bucket access, migration head, and both Celery worker pings.

### Automatic audit decision

- **The existing native AWS S3 object-storage gate remains approved for its tested local single-node scope.** This revalidates the current AWS configuration; it does not add browser CORS, lifecycle/Object Lock, account backup/restore, multi-region availability, or customer-load claims. It does not change the separate P5-1 approval or remove P5-2's model/tool-trace prerequisites.

## 2026-10-12 — P0-2 disposable persisted-baseline preparation harness (partial slice approved; P0-2 not approved)

- Added `scripts/prepare_business_evaluation.py` with a deterministic preparation manifest, an explicit same-database assertion, frozen fixture/corpus hashes, scoped corpus-document selection, disposable user/company/source/snapshot bootstrap, API-driven document creation, Worker-driven local embedding, and cleanup limited to manifest-recorded IDs. The manifest stores only an API-key SHA-256 fingerprint; no raw API key, Gold answer field, or provider credential is persisted.
- A first real preparation exposed two configuration/recovery defects. The harness initially used a generic business connection instead of the Compose-managed `acme_readonly@acme_business` read-only contract, then ran in the evaluation profile's `agent_platform_test` database while the resident API used `agent_platform`, producing a correct `401` rather than an authentication bypass. The fixed harness validates the target platform database before any write and persists the tenant cleanup IDs before the potentially failing schema discovery. The failed test-DB scope was then removed and verified empty.
- A cleanup run exposed a second defect: an ORM delete could attempt the temporary user before its `SchemaSnapshot.discovered_by_user_id` reference had been flushed away. Cleanup now uses explicit `task -> document -> snapshot -> conversation -> source -> company -> user` ordering with flushes. The exact failed run was removed and verified empty; an integration regression covers the snapshot/user ordering.
- Real no-model proof against `agent_platform`: one development knowledge case created a fresh approved tenant, discovered a ready ACME read-only schema snapshot, created the corpus document through `POST /documents`, and waited for the resident Document Worker to create positive-count chunks. A scoped audit confirmed `analysis_tasks=0`, analysis Outbox events `=0`, and model-call records `=0`; the completed scope was then cleaned with zero exact probe rows remaining. The first local embedding cold load took about 32 seconds; it is preparation latency, not a model-provider cost or request SLO.
- Submission code now keeps the ephemeral API key only in process memory, posts conversation/message requests through the real API, uses a durable request ID to recover a prior task map entry, and writes each returned task ID to the manifest. It is deliberately preflighted before bootstrap: the currently declared persisted-task default `max_cost` is `$1.00`, which exceeds the previously authorized `$0.15` ceiling, and the provider price table is unconfigured. The negative probe failed at that budget gate before reading a fixture or creating an output directory, tenant, document, task, Outbox event, or model call.
- Fresh verification: the dedicated harness suite passed `9 passed`; focused Ruff and format checks passed; changed-file `git diff --check` passed. The suite includes frozen-corpus hash mismatch, heldout exclusion, security-rejection exclusion, ACME source contract, API/test database mismatch, budget ceiling, and cleanup-order regressions.

### Automatic audit decision

- **The P0-2 preparation/cleanup sub-slice is approved. P0-2 remains not approved.** A paid real-worker task map and baseline must not start until a versioned price table and a per-task hard budget at or below the explicitly authorized ceiling are configured and independently verified. The frozen Gold fixture also currently labels three cases (`empty_document_scope`, SQL-schema injection, document injection) as request-level rejections even though the current HTTP contract has no corresponding rejection path; they must be separated into a versioned request-rejection fixture or an explicitly observed downstream security evaluation. They must not be fabricated into `rejection_map` rows or sent as ordinary analysis tasks. Heldout cases remain unused.

## 2026-10-12 — P0-2 real paid-worker smoke and automatic audit (not approved)

- The prior P0-2 note's statement that the provider price table was unconfigured was stale and is corrected here. The running API and Worker both reported `deepseek-v4-flash`, frozen price-table version `deepseek-v4.1-flash-peak-2026-10-10`, and one matching price entry. The actual defect was the task model-budget ORM default: it was `$1.00` and was not explicitly set by `create_task`.
- Server-owned settings now create and freeze a JSON-safe task budget in both the normal `create_task` path and the ORM fallback default. The client has no budget input. The current running API and Worker each reported the same budget: `max_calls=8`, `max_calls_per_node=4`, `max_repairs=2`, `max_total_tokens=16000`, `max_cost=$0.15`. Settings reject non-positive cost, invalid count relationships, and a total Token allowance smaller than one configured output allowance. A rollback-only database probe confirmed the exact persisted snapshot and left zero rows.
- Focused settings/admission/harness verification passed `25 passed`; changed-file `git diff --check` passed. The first paid read-only smoke intentionally exposed that the initial `4/2/1/8000/$0.15` policy is too small for the current normal workflow: it reached `partial/model_budget_exhausted` after four settled provider calls and `$0.0026925`, with no fifth paid call. Its terminal task, document, source, company, user, and model-call rows were then exactly cleaned.
- After retaining the same `$0.15` monetary ceiling and raising only the non-monetary limits to the frozen development fixture maximum (`8/4/2/16000`), one fresh disposable `knowledge-east-contract-evidence` run entered through the real API, Outbox and Worker against the isolated ACME read-only database and one frozen document. It ended `partial` with no error type, six settled DeepSeek calls, 9,164 Tokens, and actual durable provider cost `$0.0037005`; the public evaluation artifact reports its six-decimal settled cost as `$0.003700`. There were no reserved or unknown provider costs.
- The completed task persisted a report dictionary and the publication decision `published_partial`, not `completed`; its deterministic validation record was `unknown` even though `report_validated=true`, because the numeric and citation checks were not proved. The frozen one-case evaluation therefore honestly returned `0.00%` trusted business-analysis success and failed `route_correct`, `required_claims_supported`, `limitations_correct`, and `within_budget` (the Gold case expects at most four model calls). No security incident was recorded, but a zero-incident count does not promote an unknown hard gate to passed.
- Both paid smoke scopes were cleaned only after terminal status. Exact post-cleanup counts for each task, its model-call rows, document, source, company and user were zero. The retained manifest/artifact contains no raw API key or provider credential. Worker-first local embedding/reranker model loads were observed separately from API billing and are not request-SLO or provider-cost claims.

### Automatic audit decision

- **The budget-freezing sub-slice is approved; P0-2 and P0 remain not approved.** The real smoke proves the current price/budget ledger, API-to-Outbox-to-Worker chain, terminal partial publication semantics and disposable cleanup. It also proves the current business baseline fails its frozen quality and per-case call-budget expectations. Do not run the requested ten-task concurrency comparison or change the frozen Gold to hide this failure. The next legal slice is a source-grounded diagnosis of why the controlled workflow chose the wrong route/rejected the authorized evidence, followed by one isolated candidate change and the same baseline/candidate comparison; request-level security fixtures remain separately unresolved.

## 2026-10-12 — P0-2 source-grounded retrieval diagnosis and evaluation-image parity (diagnosis approved; P0-2 not approved)

- The first full-corpus command failed before embedding because the test resolves its corpus at container path `/docs`, while the initial invocation mounted it at `/workspace/docs`. Repeating it with the required read-only `/docs` mount reached the actual dependency boundary and then failed before retrieval because `Dockerfile.evaluation` lacked `sentence-transformers`; the Worker image alone carried the local embedding/reranker stack. Neither failure made a provider-model request or changed an evaluation tenant.
- `Dockerfile.evaluation` now installs the same CPU-only `torch==2.6.0` and `requirements-ml.txt` local-model dependencies as `Dockerfile.worker`. The rebuilt image imports `torch 2.6.0+cpu`, `sentence-transformers 5.7.0`, `LocalEmbeddingProvider`, and `LocalCrossEncoderReranker`. This permits repeatable local RAG evaluation; it does not add a cloud model provider, change runtime model behavior, or establish an endpoint SLO.
- Fresh real full-corpus evaluation used 153 frozen corpus documents and 428 generated chunk rows in the isolated test database, with corpus mounted read-only. It passed in `567.28s`. Vector retrieval measured `Recall@10=0.5033` and `MRR@10=0.2362` (development: `0.4797/0.2222`; heldout: `0.6000/0.2933`). The existing rerank stage measured `Recall@3=0.4706`, `MRR@3=0.4118`, and sufficient-evidence non-refusal rate `0.7843`. Local-model cost remains unpriced; no DeepSeek/OpenAI model call occurred.
- The failed paid Gold document `events/2025-08-east-sales-review.md` was absent from the **full-corpus** vector Top-10 candidate set. This is direct evidence of a full-corpus candidate-recall defect, and reranking alone cannot repair an item absent from its candidates. It does not by itself explain the paid smoke result: that task froze this one document ID, so a separate same-question, same-single-document retrieval reproduction is required before attributing the result to RAG rather than Planner/agent/report behavior.
- Regression after observation persistence and server-owned budgeting passed `63 passed in 2.11s`. Focused Ruff semantic checks passed with the established `EXE002,TRY004` exclusions. `git diff --check` found no whitespace error in the changed scope; Windows line-ending warnings remain. The full-file Ruff format gate remains unclosed only for pre-existing broad-format drift in three dirty files; no broad reformat was applied.

### Automatic audit decision

- **The evaluation-image local-RAG parity and the full-corpus retrieval diagnosis are approved. P0-2 and P0 remain not approved.** The current controlled baseline has a measured full-corpus candidate-recall defect and no quality promotion is permitted. It does not yet identify the paid smoke's single-document failure source. The next legal work is a same-question, same-frozen-document reproduction, followed only then by one attributable candidate comparison; it is still not authorized to run the ten-task concurrency comparison or modify Gold expectations.

## 2026-10-12 — P0-2 first retrieval-policy candidate comparison and automatic audit (candidate rejected)

- The deployed default is `paragraph_vector_rerank_v1`: paragraph chunks, vector Top-10, and local rerank Top-3. `paragraph_sliding_vector_rerank_v1` was an existing but inactive candidate that changes only the chunk-strategy set to paragraph plus sliding-window; the model, question-generation rule, tenant scope, Top-K values, reranker, and corpus remained identical.
- A deterministic 30-case **development-only** comparison ran in the isolated evaluation database. Every profile returned only candidate documents in the supplied scope (`candidate_evidence_scope_rate=1.0`). The current baseline measured `Recall@3=0.4667`, `MRR@3=0.4333`, non-refusal rate `0.8333`, and `160845 ms`. The no-rerank control measured `0.1667/0.1167/0.8333/1012 ms`, so removing reranking is rejected. The dual-chunk candidate measured `0.2000/0.1556/0.7667/79162 ms`; it is materially worse on every quality measure.
- The comparison completed `1 passed in 303.25s`. It used only local embedding/reranking weights and a test database; local-model cost is explicitly `unknown`, not zero. The frozen 30-case heldout split was not used for candidate selection and was not rerun after seeing these development results.

### Automatic audit decision

- **The dual-chunk candidate is rejected. The deployed `paragraph_vector_rerank_v1` remains unchanged, and P0-2/P0 remain not approved.** This establishes a valid negative full-corpus experiment: additional chunk variants do not repair its candidate-recall problem under the current corpus/question protocol. It must not be used to explain the separately frozen single-document paid smoke. Do not run the ten-task concurrency experiment, change Gold, or promote the candidate. The next legal diagnostic is the same-question, same-single-document retrieval reproduction.

## 2026-10-12 — P0-2 frozen single-document retrieval reproduction and automatic audit (diagnosis approved; no candidate change)

- Added a slow, opt-in reproduction using the exact Gold question `有哪些资料支持CUST-0001暂停采购？`, the exact frozen `events/2025-08-east-sales-review.md` content, the task-equivalent single `document_id` scope, the deployed paragraph retrieval policy, configured Top-10/Top-3 values, and the configured sufficiency threshold. It uses a rollback-isolated test tenant and local models only; it does not create a task, invoke a provider model, or write to the production-like evaluation tenant.
- Fresh run passed `1 passed in 123.19s`: one candidate, one reranked evidence item, score `0.8238`, and `sufficient=true`. The returned evidence belongs to the frozen document and contains both `合同` and `暂停`.
- This corrects the earlier possible attribution: the full-corpus Top-10 miss establishes a global candidate-recall defect, but **does not** explain the paid one-document smoke. The exact frozen-scope reproduction establishes that RAG can provide sufficient evidence before the paid workflow's later components. The remaining failure boundary is therefore Planner/route state, Knowledge Agent provider output/citation parsing, or subsequent reviewer/publication behavior; the cleaned historical task cannot reveal which because its normalized observation was not retained at the time.

### Automatic audit decision

- **The frozen-scope RAG diagnosis is approved; no retrieval-policy change is promoted, and P0-2/P0 remain not approved.** The next legal slice is one newly instrumented, disposable real workflow trace that persists the normalized Planner route, Knowledge tool status, parsed citations, and deterministic-review result before cleanup. It must retain the `$0.15` hard task cap and may not run the ten-task concurrency comparison, reuse heldout cases for tuning, or infer a root cause from the old cleaned task.

## 2026-10-12 — P0-2 instrumented paid trace and automatic audit (diagnosis approved; P0-2 not approved)

- One fresh development-only `knowledge-east-contract-evidence` task entered the real API → Outbox → Worker path with the same server-frozen `$0.15` hard cap. It reached terminal `partial` in `11393 ms` with eight settled provider calls, `9062` Tokens and `$0.003594` settled cost. It stayed below the monetary task cap, but fails the frozen case limits of four calls and 8000 Tokens; no conclusion has been promoted from that failure.
- The persisted evaluation artifact now retains the normalized observation before cleanup: Planner actual route `hybrid` (Gold expects `knowledge_only`), entity `CUST-0001`, no returned report citations, partial outcome, report persisted, deterministic validation `unknown`, and zero security incidents. This proves the Planner-route mismatch; it does not establish why the model chose `hybrid` or authorize a prompt/route change.
- Pre-cleanup metadata-only audit closes the Knowledge/Reviewer boundary without exposing prompts or business-report bodies: `rag_search` completed `succeeded/ready` in `958 ms`; `knowledge_result` was `ready` with one evidence item and a non-empty answer; Reviewer received one citation chunk ID and marked knowledge available. Its semantic-review verdict was `partial`, so the existing Reviewer safety branch deliberately cleared `document_citations`, set report status to `partial`, and recorded `citation_relevance_unverified`. The later deterministic citation check therefore remained `unknown`. This is intentional fail-closed behavior, not a citation-ID mapping loss.
- Cleanup completed after the artifact was written. Exact post-cleanup counts for task `81`, its model-call rows, document, source, snapshot, conversation, company and user were all zero; the manifest records cleanup state `completed`. The retained trace contains only the normalized evaluation artifact and manifest. The earlier full-corpus RAG failure and the Planner route mismatch are independent observations and must not be collapsed into a single cause.

### Automatic audit decision

- **The instrumented trace is approved as diagnostic evidence; P0-2 and P0 remain not approved.** Two independently measured gaps remain: Planner route selection for this document-only question, and the semantic-review contract that downgrades the otherwise evidence-backed Knowledge answer. No candidate change is promoted. The next legal work is a one-variable, development-only candidate targeted at one of those gaps with an explicit safety/rollback test; heldout cases and the ten-task concurrency comparison remain out of scope.

## 2026-10-12 — P0-2 persisted control-flow observation slice (approved; P0-2 not approved)

- `EvaluationObservation` now retains privacy-safe control-flow facts from already-persisted terminal `result_data`: Planner intent kind, Knowledge result status and evidence count, semantic-review verdict, and Reviewer citation-ID count. It stores no prompts, model answers, document excerpts, checkpoint body, raw tool parameters, or credentials. The adapter regression constructs the corresponding persisted fields and verifies their exact normalized values; focused evaluation/CLI/admission/settings regression passed `63 passed`, with focused Ruff and format checks passing.
- A fresh diagnostic trace using those fields reproduced the baseline shape: `business_cause/hybrid`, Knowledge `ready` with one evidence item, Reviewer citation-ID count one, semantic verdict `partial`, terminal partial, eight observed model records, 9119 Tokens and `$0.003627` settled cost. The disposable task and all associated rows were then cleaned to zero. This establishes that later cleanup no longer erases the control-flow boundary needed to explain a paid smoke.

### Automatic audit decision

- **The control-flow observation slice is approved. P0-2/P0 remain not approved.** It improves evidence retention only; it neither repairs routing nor changes citation safety. The next candidate remains subject to one-variable comparison and rollback.

## 2026-10-12 — P0-2 Planner document-support routing candidate and automatic audit (candidate rejected and rolled back)

- Candidate variable: one explicit Planner instruction that a narrow question asking which documents support, record or explain a specified matter—without a request for data validation, comparison or causal attribution—must choose `document_question` and `knowledge_only`, rather than `hybrid` merely because the document includes numbers. A dedicated prompt-contract test plus Planner/workflow/evaluation regression passed `150 passed`; focused static and format checks passed after excluding documented pre-existing `FLY002`/`ISC004` whole-file style debt.
- In the real development-only candidate trace, the first route was corrected to `document_question/knowledge_only`, and Knowledge again returned one evidence item. This improvement was insufficient: semantic review still returned `partial`, the existing fail-closed Reviewer branch removed report citations, and the deterministic result remained unknown. The smart router then initiated a second full Planner → Knowledge → Reviewer cycle. The final task used eight settled DeepSeek calls (the configured maximum), four local resource records, 10315 Tokens, and `$0.0040791` settled provider cost. It stayed below `$0.15`, but failed the frozen case call/Token limits and did not satisfy required claims or limitations.
- The candidate task, model-call records, company and user were verified at zero after cleanup; API readiness remained fully `ok` and the broker queue was zero. The Planner instruction and its dedicated candidate test were then rolled back and the Worker rebuilt, so the rejected route rule is not left active as a default.

### Automatic audit decision

- **Reject the Planner routing candidate.** It corrected a local route label but caused a bounded replan loop and did not close the semantic/citation gate, so it is not an improvement on the frozen development case. P0-2/P0 remain not approved. The next legal target is the separate semantic-review contract for narrow document-question evidence; do not combine it with Planner changes, use heldout data for tuning, alter Gold, or run the ten-task concurrency comparison.

## 2026-10-12 — P0-2 narrow document-evidence contract candidate and automatic audit (candidate rejected and rolled back)

- Candidate scope was limited to the narrow document-support contract: a `supported` semantic review could persist a separately typed, citation-bound document finding; `partial`, `unsupported`, a refuted controlled-data claim, or a failed final citation check still cleared that finding. The numeric validator was also made inapplicable to pure-document identifiers when no SQL row value existed. Focused positive and negative tests covered all four rejection paths; the preflight suite passed `81 passed`, then the post-rollback suite passed `98 passed`. Targeted Ruff (with only the pre-existing executable-bit `EXE002` excluded), selected format checks, and scoped `git diff --check` passed.
- One fresh development-only `knowledge-east-contract-evidence` task used the real API → Outbox → rebuilt Worker path, one frozen document, the ACME read-only business source, and the server-owned `$0.15` task cap. It reached `partial` in `70631 ms`, produced `8` model-call records, `9163` Tokens, and `$0.003607` settled provider cost. No second submission or heldout case was used.
- The candidate did close the intended intermediate boundary: persisted diagnostics show Planner `business_cause/hybrid`, Knowledge `ready` with one evidence item, semantic verdict `supported`, one Reviewer citation ID, citation validation `passed`, numeric validation `passed`, and deterministic validation `passed`. The report's direct document statement described the July contract expiry and paused procurement, with the document's renewal uncertainty retained as a limitation.
- It nevertheless failed the frozen case's whole gate: route remained `hybrid` rather than `knowledge_only`; the eight recorded calls and 9163 Tokens exceeded the case's `4/8000` limits; the model split the target wording across clauses so the literal required-claim matcher did not match; and `citation_scope_correct` failed because this dynamically prepared tenant assigned chunk ID `18` while the Gold case has no stable `allowed_chunk_ids` value and the evaluator currently interprets its empty default as “no citations allowed”. The last item is an evaluation-contract defect, not evidence of an unauthorized citation: the returned document was the frozen scope and citation validation passed.
- The task, its model-call records, document, source, snapshot, conversation, company, user, and related scope rows were cleaned after the evaluation artifact was written; exact checks confirmed task `84` and its call records were zero. The semantic/report/numeric candidate source was then reverted and the Worker rebuilt to the prior baseline. The candidate is not promoted.

### Automatic audit decision

- **Reject the narrow document-evidence candidate as a production/default change. P0-2/P0 remain not approved.** It demonstrates an intermediate evidence-publication improvement but fails the frozen route and budget gates, and its full case still cannot pass until the evaluator's dynamic-chunk contract is corrected without weakening document-scope or citation-validation checks. The next legal slice is a test-first P0 evaluation-contract repair for “unspecified dynamic chunk IDs” versus “explicit forbidden IDs”; it must not change Gold business expectations, use heldout cases, or restart the concurrency experiment.

## 2026-10-12 — P0-2 dynamic citation-scope evaluation contract repair (sub-slice approved; P0-2 not approved)

- The prior candidate artifact revealed two independent evaluator defects. First, Gold cases that omit `allowed_chunk_ids` are prepared in fresh tenants where chunk IDs are dynamic, but the old schema defaulted an omitted value to `[]`, which the evaluator interpreted as an explicit ban on every returned citation. `EvaluationCase.allowed_chunk_ids` now distinguishes `None` (unspecified dynamic IDs: check the frozen document path plus runtime citation validation) from explicit `[]` (deny any returned chunk). The strict explicit-empty denial regression remains and a new dynamic-ID success regression proves the opposite case.
- Second, content-submitted frozen documents have no storage `file_path`; their controlled preparation records the relative corpus path in `Documents.source`. The observation adapter now uses `file_path` when present and otherwise that persisted source label when resolving cited chunk paths. Parameterized regression covers both file-upload and content-submitted forms and preserves the independent database-backed frozen-document security check.
- Focused evaluation/harness/observation suite passed `49 passed`; targeted Ruff passed with only established `EXE002`/`TRY004` exclusions; selected format checks and scoped `git diff --check` passed. The restored baseline Worker reported both Celery nodes online.
- Re-evaluating the historical candidate observation with its verified frozen document path under the repaired contract makes `citation_scope_correct=true`; remaining violations are exactly `route_correct`, `required_claims_supported`, `limitations_correct`, and `within_budget`, with entity/result-fingerprint telemetry still `unknown`. This is a deterministic contract replay, not a new paid run and not a full candidate pass.

### Automatic audit decision

- **Approve this P0 measurement-contract sub-slice only. P0-2/P0 remain not approved.** The repair makes dynamic evaluation identities explicit while retaining explicit chunk denial, document-path scope, and runtime citation checks. It does not repair Planner routing, model phrasing, route-independent limitation handling, or the four-call/eight-thousand-token case budget; no Gold expectation, heldout case, or concurrency experiment was changed.

## 2026-10-12 — P0-2 provider-call versus local-resource accounting repair (sub-slice approved; P0-2 not approved)

- `ModelCallRecord` already distinguishes `charge_kind="provider_model"` from `charge_kind="local_resource"`, but the evaluation observation had used the total record count as `model_calls`. That mixed paid/provider LLM decisions with local embedding and reranking resource records, despite their different budget and cost semantics.
- The observation now counts only `provider_model` records toward `model_calls` and retains a separate non-negative `local_resource_calls` diagnostic. A persisted-task regression creates two provider records and one local reranker record and proves the observation reports `2` and `1` respectively. Local resources remain in the durable ledger and no cost is silently set to zero.
- Focused evaluation/harness/observation suite passed `49 passed`; targeted Ruff and scoped `git diff --check` passed. This changes future normalized observations only; the cleaned historical candidate artifact is not rewritten and no paid task was run.

### Automatic audit decision

- **Approve this P0 measurement-contract sub-slice only. P0-2/P0 remain not approved.** The repair clarifies the frozen call-budget metric but does not establish that any workflow now meets it. Planner routing, literal evidence-claim extraction, limitation semantics, and a fresh real baseline/candidate comparison remain required before the ten-task concurrency experiment.

## 2026-10-12 — P0-2 provider-call-by-node observation repair (sub-slice approved; P0-2 not approved)

- The cleaned real task artifacts retained the total provider-call count but not its node distribution. An eight-call budget breach could therefore not be attributed to Planner, Knowledge, Reviewer or semantic-review repair/retry behavior without guessing. This blocks a valid one-variable candidate.
- `EvaluationObservation` now derives the privacy-safe `provider_model_calls_by_node` map from durable `ModelCallRecord.node_name`, counting only `charge_kind="provider_model"`. Local embedding/rerank records remain separate in `local_resource_calls`; the map contains no prompt, response, tool parameters, document text, credentials, or provider payload.
- The red regression first failed because the observation contract did not expose this field. After the minimal adapter change, evaluation observation/business/CLI regressions passed `40 passed`; changed-file Ruff passed with only the established `EXE002`/`TRY004` exclusions, selected format checks passed, and scoped `git diff --check` passed. The unrelated P1-2 model/tool-contract pre-research files were removed rather than left as an unapproved next-phase change.

### Automatic audit decision

- **Approve this P0-2 measurement sub-slice only. P0-2/P0 remain not approved.** It establishes the missing attribution needed for one new disposable development baseline. It does not alter a model prompt, Agent route, semantic-review policy, report schema, Gold expectation, Worker budget, or any heldout case. The next legal action is one fresh development-only real baseline under the existing `$0.15` hard cap, then inspect its per-node observation before proposing a candidate.

## 2026-10-12 — P0-2 interrupted-preparation recovery and document-route candidate (candidate rejected; P0-2 not approved)

- A first candidate preparation was interrupted at the command-observation boundary after `POST /documents` created an evaluation document but before the old manifest recorded it. The old cleanup then correctly refused to delete the company because the unrecorded document still held the restrictive foreign key. The incident exposed a harness recoverability defect, not a business-result fact. The former background container later submitted task `86`, but its terminal task and ledger were cleaned before a normalized evaluation was written; it is explicitly excluded from all baseline/candidate conclusions.
- The harness now persists each document ID and frozen path immediately after the API create response and before waiting for its Worker result. Cleanup now discovers and deletes all documents within the disposable company scope, rather than trusting a possibly interrupted manifest alone. Red regressions cover both the creation-to-wait interruption and a manifest with an omitted document; the focused harness suite passed `10 passed`, then the combined P0 suite passed `145 passed`, with selected Ruff, format, and scoped diff checks clean. The real orphan company `27`, document `14`, source, snapshot, user, and all related task rows were subsequently verified absent.
- One new named, independently monitored real candidate task `87` used the same frozen development case, one authorized document, read-only ACME demo database, API → Outbox → Worker path, and `$0.15` hard cap. Its persisted evaluation was written before cleanup. The only business candidate variable was a deterministic `document_question -> knowledge_only` route normalization, applied after model parsing without another model repair call.
- Compared with the fresh baseline task `85`, the candidate corrected route `hybrid -> knowledge_only`, reduced provider calls `6 -> 4`, tokens `9008 -> 5057`, settled provider cost `$0.003561 -> $0.002042`, and duration `82833 ms -> 7801 ms`. Its settled provider calls were exactly Planner `1`, semantic review `1`, Knowledge `1`, Reviewer `1`; local embedding/rerank calls remained separately recorded as `2`. These are real task-ledger facts, not simulated costs.
- The candidate nevertheless failed frozen hard gates `required_claims_supported` and `limitations_correct`, with trusted business-analysis success still `0.00%`. It therefore cannot become a baseline or default change. Source review identifies a structural contract mismatch: `ConfirmedFact` requires data evidence; `Hypothesis` requires a confirmed data fact plus a citation; `compose_report` emits hypotheses only when both data facts and citations exist; and the Reviewer deliberately removes hypotheses and document citations whenever semantic review is not `supported`. A document-only question can therefore retrieve the correct frozen chunk yet have no supported document finding to publish.
- The route-normalization source and its red test were rolled back after the failed evaluation. Task `87`, its model-call records, company `28`, user `36`, source `21`, snapshot `21`, document `15`, and the named evaluation container were cleaned only after the report was retained; exact post-cleanup probes returned zero for every listed resource. No raw API key or provider credential is stored in the artifact.

### Automatic audit decision

- **Approve the interrupted-preparation recoverability repair as a P0 measurement sub-slice. Reject the document-route candidate as a default change. P0-2/P0 remain not approved.** This is the third isolated P0 candidate failure (after the route-prompt and narrow-document-report candidates). Per the debugging gate, do not add a fourth prompt, route, semantic-review, or evaluator patch. The next work requires an explicit architecture decision for a document-cited finding/report contract that is distinct from data-backed facts and causal hypotheses, including its deterministic validation and frozen evaluation semantics. No P1/P5 work and no concurrency comparison may start first.

## 2026-10-12 — P0-2 document-finding architecture candidate and frozen-Gold audit (not approved)

- Implemented the planned typed `DocumentFinding` contract (`schema_version=1.2`) separately from data-backed `ConfirmedFact` and causal `Hypothesis`. A finding must cite existing document chunks; failed reports cannot contain one; a completed report may contain a direct document finding without a data fact. The observation adapter includes retained document findings in `actual_supported_claims`.
- The candidate also made the preparation poll respect the API-key rate limit: the old 0.5-second document-status poll could exceed the API's 100-request-per-minute sliding window before the 90-second timeout. The harness now polls once per second and retains a document ID before waiting, so failed preparation remains exactly cleanable. The first live preparation failed at that known 429 boundary before task submission or model cost; its temporary scope was cleaned from the manifest.
- First real architecture run `88` was rejected before promotion: Planner persisted `business_cause/hybrid`, which invoked Data and consumed six provider-model calls. The evidence semantic review did explicitly return `supported_document_chunk_ids=[28]`, but the Reviewer correctly refused to use it because the Plan did not have the document-question contract. Its formal candidate artifact recorded `route_correct=false`, `required_claims_supported=false`, `limitations_correct=false`, `within_budget=false`, deterministic validation `unknown`, and settled provider cost `$0.003691`.
- A narrow deterministic guard now normalizes explicit Chinese document-evidence requests such as `有哪些资料支持...` to `document_question/knowledge_only`; it does not alter causal questions. The Planner prompt documents the same distinction. Numeric validation now accepts an answer number only when it appears exactly in either controlled SQL output or the specific retrieved/cited document content; separate regressions reject a number absent from both sources. Direct-document findings remain fail-closed unless the semantic reviewer explicitly supports retrieved chunk IDs.
- Fresh candidate `89` used one frozen document, the ACME read-only demo source, real API -> Outbox -> Worker processing, and the server-owned `$0.15` cap. It met the operational candidate expectations: `knowledge_only`, `document_question`, 4 provider-model calls (Planner, semantic review, Knowledge, Reviewer), 2 local-resource records, 5,249 tokens, `$0.002024` settled provider cost, one returned frozen document path, and passed numeric, citation, report-schema, deterministic-validation and security-scope checks. The report persisted one cited direct document finding. Its disposable task, ledger rows, document, source, snapshot, company and user were cleaned only after the evaluation artifact was written.
- The frozen one-case Gold nevertheless returned `hard_gate=failed`: the direct finding was semantically supported but did not contain the literal expected substring `合同到期后暂停采购`; the semantic review was `supported`, so its non-empty uncertainty notes were not published as the literal expected limitation `仍需人工确认续约结果`. More fundamentally, this case declares `expected_route=knowledge_only` while also requiring an SQL query requirement and result fingerprint. A correct knowledge-only execution has no SQL result fingerprint, which the evaluator classifies as an unknown hard gate. Therefore this frozen case cannot be promoted by another prompt or wording change without changing either the Gold/evaluator contract or the stated knowledge-only route.
- Verification before the last real run: the combined targeted P0 suite passed `197 passed in 9.55s`; changed-scope Ruff passed with the established exclusions; 16 changed files passed `ruff format --check`; and `git diff --check` passed. These tests prove the stated contracts, not that the frozen business case passed.

### Automatic audit decision

- **P0-2 and P0 are not approved.** Do not start P1/P5, the requested ten-task concurrency comparison, or another paid candidate. The next required decision is an evaluation-contract decision: either create a newly versioned development Gold that makes SQL/fingerprint gates explicitly inapplicable for document-only cases and expresses document claims/limitations in a deterministic schema, or redefine this case as hybrid and supply the corresponding SQL expectation. The existing frozen Gold and its artifact remain unchanged.

## 2026-10-12 — P0-2 route-aware evaluation-contract v1.1 preparation (sub-slice approved; P0-2 not approved)

- The original immutable `business-gold-v1` fixture is unchanged and still loads as its original 23-development/7-heldout set. `EvaluationCase` now permits explicit inapplicability only for the already recognized scope gates plus the two SQL-specific gates `sql_result_equivalent` and `numeric_consistent`; those two SQL gates can be marked inapplicable only when the frozen expected route is `knowledge_only`. A data or hybrid case attempting the same exemption is rejected at schema validation, so the change cannot silently bypass SQL checks for a route that claims to use data.
- Added `business-knowledge-development-v1.1`, a four-case development-only subset copied from the existing document-question expectations and budgets. It contains no heldout cases and changes no original Gold expectation. Each case explicitly records that SQL-result equivalence and SQL numeric consistency do not apply to a knowledge-only route; entity and citation scope, required claims, outcome, limitations, deterministic validation, security, call and token budgets remain applicable.
- Focused evaluator regression passed `23 passed in 0.33s`; it loads the v1.1 fixture, verifies all four cases are development-only and `knowledge_only`, verifies the exact two exempt gates, proves a knowledge-only observation no longer receives an unavoidable SQL `unknown`, and proves a data-route exemption is rejected. Focused Ruff and `git diff --check` passed; Windows line-ending warnings are pre-existing workspace noise.
- This is a measurement-contract repair only. It does not make document evidence assertions semantic, does not relax document-path/citation validation, does not resolve the literal claim mismatch or missing limitation semantics, does not promote the reverted document-finding candidate, and incurred no provider-model cost.

### Automatic audit decision

- **Approve only this P0-2 evaluation-contract sub-slice. P0-2/P0 remain not approved.** The next legal work is to define and test a deterministic, versioned document-finding claim/limitation contract before any new paid development trace. Do not run P1/P5 work, the ten-task concurrency comparison, a heldout case, or another prompt/route candidate first.

## 2026-10-12 — P0-2 rejected document-finding candidate rollback correction and runtime dependency check (not approved)

- Source audit found that the previous rejected candidate's Composer/Reviewer route was still capable of publishing a new `DocumentFinding`, despite the earlier ledger statement that the candidate source had been reverted. This was a rollback defect: an unapproved default behavior must not remain runnable merely because its focused candidate test had once passed.
- The normal Composer/Reviewer path no longer creates or publishes a direct document finding, no longer asks semantic review for candidate-specific supported chunk IDs, and the observation adapter no longer treats a document finding as a supported claim. Candidate-only Composer, Reviewer and observation assertions were removed; unrelated report-schema compatibility fields were not broadly reset. The focused reporting/evaluation suite passed `50 passed in 2.32s`, focused Ruff passed with established exclusions, and `git diff --check` passed. API, Worker and report-worker were rebuilt from this source; no provider-model request occurred.
- Post-rebuild readiness is currently **not** acceptable for a real P0 trace: database and Redis are `ok`, but the configured S3 `HeadBucket` probe returns HTTP `403 Forbidden`, so readiness reports `object_storage=unavailable` and task capacity is not evaluated. Configuration presence is confirmed inside the API container; no credential value is recorded here. A 403 is consistent with missing `s3:ListBucket` or an explicit bucket-policy deny, but does not alone prove which one.

### Automatic audit decision

- **The rollback correction is approved as a containment sub-slice; P0-2/P0 remain not approved.** No paid trace, P1/P5 work, heldout case, or concurrency comparison may start while object-storage readiness is unavailable. Restore the minimum bucket-level permission or remove any conflicting bucket-policy deny, then rerun the read-only readiness probe before returning to the versioned document-finding evaluation design.

## 2026-10-12 — P0-2 deterministic document-term evaluation contract v1.2 (sub-slice approved; P0-2 not approved)

- The frozen `business-gold-v1` remains untouched. Added a separate four-case, development-only `business-knowledge-development-v1.2` fixture. It replaces only the v1.1 subset's brittle literal document-claim and limitation strings with versioned `all_of` term groups; it retains question, company, document scope, entity, period, outcome, SQL-gate inapplicability, call budget and token budget. It contains no heldout case.
- `RequiredTerms` rejects empty and repeated terms. Document-term expectations are allowed only for `knowledge_only` cases and cannot be mixed with the legacy literal claim/limitation expectations. The evaluator deterministically requires every term group to occur in one persisted output item; it does not call an LLM as judge. Missing one required term fails the existing `required_claims_supported` gate. Citation path/scope, runtime citation validation, entity/period, publication, deterministic validation, security, and budget gates remain separate applicable gates.
- Focused evaluation contract verification passed `26 passed in 0.36s`, including wording variation that passes only when all required terms are present, a missing-term failure, v1.2 fixture loading, and the existing data-route SQL-exemption rejection. Focused Ruff and `git diff --check` passed. No provider-model call, heldout fixture, or runtime behavior change was made.
- This static contract does **not** publish a document finding or prove that current runtime output contains the required terms. Its purpose is to make the next candidate's evaluation deterministic once object storage is healthy. The active readiness blocker is unchanged: the configured bucket `HeadBucket` probe still returns 403.

### Automatic audit decision

- **Approve only the v1.2 evaluation-contract sub-slice. P0-2/P0 remain not approved.** The next required condition is S3 readiness. After it is restored, re-run readiness, then implement and test one runtime document-finding publication slice against v1.2 before any paid development trace. Do not advance to P1/P5, heldout evaluation, or the ten-task concurrency comparison.

## 2026-10-12 — P0 external object-storage readiness diagnosis refinement (blocked)

- A repeated read-only `HeadBucket` probe still returned HTTP 403, so readiness remains unavailable with database and Redis healthy. A separate STS `GetCallerIdentity` probe using the same configured object-storage credentials returned `InvalidClientTokenId` before any bucket authorization check.
- This is stronger evidence than the earlier 403 inference: the configured access-key/secret pair is invalid, inactive, mismatched, or not the pair that belongs to the intended AWS account. It must be corrected before judging bucket IAM actions such as `s3:ListBucket` or bucket-policy denies. No bucket, object, task, or provider-model call was created.

### Automatic audit decision

- **P0-2/P0 remain blocked by invalid external credentials.** Create or reactivate an IAM access key for the intended least-privilege user, update the local secret values without printing them, restart the affected containers, and re-run STS then readiness. Retain the planned bucket-level `s3:ListBucket` permission for the health probe, but do not diagnose its policy until STS succeeds.

## 2026-10-12 — P0 external object storage recovered and document-finding publication candidate preflight (not yet approved)

- The local object-storage credentials differed from the values already loaded by the running containers. Recreating API, Worker and report-worker loaded the updated local configuration. Read-only verification now passes in order: STS identity, S3 `HeadBucket`, and application readiness (`database`, `redis`, `object_storage`, and `task_capacity` all `ok`). No credential value, bucket object, or model request is retained in this ledger.
- Reintroduced a deliberately narrow candidate: only a `knowledge_only` `document_question` whose semantic review explicitly names retrieved chunk IDs may publish a `DocumentFinding`. The Reviewer filters finding citations to that subset; unsupported, missing, or non-retrieved IDs retain the fail-closed branch. Semantic limitation messages keep the result `partial` rather than silently converting an uncertain document statement into a completed report. Observation maps the persisted finding to supported claims for evaluation.
- Numeric validation now accepts a displayed number only if it is present in controlled SQL output **or** in the same retrieved cited text supplied to final-answer validation. It does not allow model-only numbers. Focused reporting/evaluation preflight passed `55 passed in 2.31s`; focused Ruff and `git diff --check` passed. API/Worker/report-worker were rebuilt from this source and readiness returned `ok`.
- This is still preflight evidence, not a real workflow result. Planner routing is unchanged; no paid development task, heldout case, concurrency run, or default promotion has occurred.

### Automatic audit decision

- **The external readiness repair is approved and the document-finding candidate is admitted only to one disposable development trace. P0-2/P0 remain not approved.** The next legal action is exactly one real `knowledge-east-contract-evidence` run against the v1.2 development fixture with the existing `$0.15` hard cap, artifact-before-cleanup, and automatic rollback if any hard gate fails. Do not alter Planner routing or run a second paid task first.

## 2026-10-13 — P0-2 v1.2 real document-finding trace, source-scope audit, and v1.3 contract correction (not approved)

- One authorized development-only task (`90`) was run through the real API -> Outbox -> Worker path against the frozen `knowledge-east-contract-evidence` document, ACME read-only demo business database, `deepseek-chat`, and the existing server-owned `$0.15` cap. The persisted artifact records `knowledge_only` / `document_question`, one ready knowledge evidence item and one frozen-path citation, semantic verdict `supported`, four provider calls (Planner, semantic review, Knowledge, Reviewer), two local-resource calls, 5,113 Tokens, 68,101 ms, and settled provider cost `$0.001980`. Runtime citation, numeric, deterministic-validation, and security-scope checks passed; the disposable scope cleanup is recorded as completed. No provider credential is stored in the artifact or this ledger.
- The candidate correctly stated that the July contract had expired and CRM/business material recorded paused ordinary procurement. It failed exactly `limitations_correct`; its retained limitation was an unsupported request for an independent original document/formal decision. `entity_scope_correct` telemetry was unknown, not a violation, because this document-only observation has no persisted entity/period extractor value. This remains a rejected candidate and cannot become the P0 baseline or default behavior.
- Frozen-source audit found the evaluator target itself was wrong for the question. The East document never says that renewal needs further confirmation; its actual boundary is that a competitive quote is only a background signal and cannot alone prove the unique cause of all East-region sales decline. More importantly, the question asks only which material supports CUST-0001 pausing procurement. That narrow support answer is complete when it cites the authorized document; an unrelated broader causal caveat must not force `partial`. The three other development sources were reviewed by the same rule: the batch-anomaly and receivable-risk support questions are complete at their stated scope; only the margin-factor question needs a source-grounded no-single-cause qualification.
- Added development-only `business-knowledge-development-v1.3`; v1.2 and immutable `business-gold-v1` remain unchanged. v1.3 changes outcome/qualification expectations from the frozen question and source scope, not from task 90 wording: three narrow support questions are `completed` with no required limitation, and the margin question remains `partial` with `不能` + `只归因` as its required document-boundary terms. New regression makes those distinctions explicit. A separate Composer regression proves the currently contained document-only path remains `partial` with no `DocumentFinding`, so this fixture is not falsely presented as a current runtime pass.
- Verification after the correction: focused reporting/evaluation suite `56 passed in 2.56s`; changed-scope Ruff passed with only the existing Windows executable-bit `EXE002` excluded; both changed test files were formatted; `git diff --check` passed (line-ending warnings are pre-existing workspace noise). Application readiness is `ok` for database, Redis, object storage, and task capacity. No new provider-model request, heldout run, P1/P5 work, or concurrency comparison occurred.

### Automatic audit decision

- **Approve only the source-scope v1.3 evaluation-contract sub-slice. P0-2/P0 remain not approved; do not run another paid trace yet.** Three prior candidate failures demonstrate an architecture error, not a prompt-wording deficit: the report contract conflates an incomplete answer (`partial` plus operational limitation) with a complete document-supported answer that must carry a source-bound qualification. The next required P0-2 slice is one architecture decision and red tests for a typed, citation-bound document qualification that can coexist with `completed`; generic semantic-review limitations must not silently downgrade a complete narrow answer, and source qualifications must not be discarded. A further hard prerequisite is exposed by task `90`: `PlannerDecision.evaluation_scope` was absent, so Worker `_evaluation_facts` persisted null entity/period and the observation correctly records scope as `unknown`. The next design must add a server-proven document-task scope source or deliberately stop before execution when such a source is unavailable; it must not use the evaluation fixture, model guesswork, or an entity-scope exemption. Only after both contracts, their deterministic validation, containment/rollback paths, and focused tests are reviewed may one new disposable v1.3 development trace use the existing `$0.15` cap. Do not change the frozen Gold, run heldout data, or start P1/P5 first.

## 2026-10-13 — P0-2 document qualification and document-route scope contracts (candidate preflight; no paid trace)

- The report contract now separates a document's source-stated boundary from an incomplete answer. `DocumentFinding` may carry typed `DocumentQualification` records while its report remains `completed`; each qualification must cite only chunks already cited by the finding. This does not allow a generic `Limitation` on a completed report, and a `partial` report still requires an operational or evidence insufficiency limitation.
- Semantic review may return proposed document qualifications with chunk IDs, but Reviewer retains one only when every referenced ID is among its semantic-supported retrieved chunks **and** the proposed statement occurs verbatim in the retrieved content. Invalid IDs, paraphrases, or invented restrictions are discarded. A document question without semantic-supported chunks remains fail-closed: its finding and citations are cleared and the response is partial. The old generic semantic-review `limitations` array no longer silently downgrades a supported narrow document answer; it remains diagnostic metadata rather than a published source boundary.
- Evaluation observation now persists document qualifications separately. `business-knowledge-development-v1.3` expects the margin case's `不能` + `只归因` as a qualification in a `completed` result, rather than as a `partial` limitation. For all four document-only cases, `entity_scope_correct`, SQL-result equivalence, and SQL-numeric consistency are explicitly inapplicable only because the frozen-document citation gate remains applicable and the document claim terms themselves require the named business object. Schema validation now rejects an entity-scope exemption on data or hybrid routes. This corrects the earlier over-broad statement that a document-only route must invent Planner entity/period telemetry; it does not exempt tenant, task-document, returned-path, citation-validation, claim, outcome, security, budget, or publication checks.
- Red tests first failed because the qualification type did not exist. Green verification then passed `81` focused reporting/evaluation/semantic/worker tests and `129` workflow-inclusive tests. The tests cover cited qualification acceptance, uncited qualification rejection, semantic partial fail-closed behavior, no-semantic document-question fail-closed behavior, and rejection of a non-verbatim fabricated qualification. Changed-scope Ruff passed with only existing Windows executable-bit `EXE002` excluded; selected format checks and `git diff --check` passed.
- API, Worker and report-worker were rebuilt from this source. A retried read-only readiness probe returned `database=ok`, `redis=ok`, `object_storage=ok`, and `task_capacity=ok`. No DeepSeek/provider call, fixture preparation, disposable tenant, heldout run, P1/P5 work, or concurrency comparison occurred in this slice.

### Automatic audit decision

- **Approve this P0-2 architecture/preflight sub-slice only. P0-2/P0 remain not approved.** The next permitted evidence is exactly one disposable `knowledge-east-contract-evidence` trace using `business-knowledge-development-v1.3`, the frozen single document, the existing ACME read-only database, artifact-before-cleanup, and a new explicit per-task provider-cost authorization capped at `$0.15`. Promotion still requires the persisted observation to pass every applicable hard gate; on failure, retain the artifact, clean the temporary scope, and contain/rollback the candidate. Do not use v1.3 on heldout data or begin P1/P5/concurrency work first.

## 2026-10-13 — P0-2 v1.3 one-task real trace (failed; P0 remains blocked)

- Under one explicit `$0.15` authorization, submitted exactly one development-only `knowledge-east-contract-evidence` task (`91`) through real API -> Outbox -> Worker execution. The prepared scope used one frozen East-sales document and the ACME read-only demo source. The persisted evaluation artifact is `backend/.evaluation-runs/p0-2-document-finding-v1-3/evaluation/run.json`; it was written before cleanup. No heldout case, second analysis task, P1/P5 work, or concurrency comparison ran.
- The provider cost settled at `$0.003709`, below the authorized `$0.15` cap, but the run is still a hard failure: six provider calls and 9,262 tokens exceeded this case's frozen 4-call and 8,000-token caps. The terminal report was `partial`; the persisted route was `hybrid`, intent `business_cause`, semantic verdict `partial`, and there were no retained supported claims, document qualifications, returned paths, or returned chunk IDs. The evaluator recorded violations of `route_correct`, `required_claims_supported`, `outcome_correct`, and `within_budget`; citation scope and deterministic validation remained `unknown`. Security passed and the report was persisted, but those facts do not offset a hard-gate failure.
- Root-cause trace: `PlannerDecision` only normalizes the route when the model has already returned `intent.kind=document_question`. The real Planner instead returned `business_cause` for the explicit document-evidence question, so the workflow legally chose `hybrid`, invoked the Data node twice, and reached the generic partial-report path. The focused tests construct `document_question` directly and therefore did not exercise the required question-to-intent boundary. This is a deterministic routing-contract gap, not a provider-cost, authorization, object-storage, or citation-validator failure.
- After artifact creation, cleanup was limited to the manifest-recorded disposable IDs. A direct post-cleanup database check returned zero rows for task `91`, company `33`, document `20`, user `41`, data source `26`, and schema snapshot `26`; a read-only readiness check still reports database, Redis, object storage, and task capacity `ok`.

### Automatic audit decision

- **Reject the v1.3 runtime candidate; P0-2/P0 remain blocked.** Do not promote its typed document-finding/qualification behavior, begin P1/P5, run the ten-task concurrency comparison, use heldout data, or spend another provider call. The next permitted no-cost slice is a deterministic question-to-document-intent routing contract at the Planner boundary, with a red regression reproducing this exact Chinese question and an end-to-end persisted-plan assertion that Data is not selected. It must preserve fail-closed behavior for ambiguous or causal questions. Only after its code, containment/rollback boundary, and static evidence pass a fresh audit may the user authorize one further disposable development trace.

## 2026-10-13 — P0-2 explicit document-evidence routing boundary (candidate preflight; no paid trace)

- The failed task `91` is now reproduced as a deterministic contract: when the model returns `business_cause` / `hybrid` for `有哪些资料支持CUST-0001暂停采购？`, the shared PlannerDecision boundary replaces only that explicit document-evidence interpretation with `document_question` / `knowledge_only`. It intentionally recognizes only questions beginning with `有哪些` or `有些` plus `资料`/`文档` and `支持`/`说明`; it is not a broad intent classifier. A direct causal question about whether the same pause was the sole cause of East-region decline remains `business_cause` / `hybrid`.
- The first implementation failed its new red test because the expression omitted the literal `有哪些` form; the corrected expression passes. A second red test found that the post-Planner semantic review could replace the protected plan with a new `business_cause` / `hybrid` decision. The guard was therefore moved to `planner_decision.py` and is now applied both after Planner parsing and before semantic-review output is written back to workflow state. The Graph regression proves the resulting plan selects `knowledge_node`, not `data_node`.
- Verification: targeted Planner/decision/workflow regressions passed `52 passed`; the relevant analysis/workflow/reporting/evaluation suite passed `335 passed, 4 skipped`; selected Ruff passed with established `EXE002`, `FLY002`, and `ISC004` exclusions; selected format and `git diff --check` passed. API, Worker and report-worker were rebuilt. A direct no-model contract execution inside the rebuilt Worker printed `worker-shared-contract-ok`; the retried read-only readiness probe returned database, Redis, object storage, and task capacity `ok`.
- No provider call, disposable tenant, document upload, evaluation task, heldout case, P1/P5 work, or concurrency comparison occurred in this slice. The prior v1.3 runtime artifact remains the failure record; this is static and runtime-image preflight only, not evidence that the real task now passes.

### Automatic audit decision

- **Approve only this no-cost routing-containment preflight. P0-2/P0 remain unapproved.** The next required evidence is exactly one newly authorized disposable `knowledge-east-contract-evidence` development trace with the existing frozen v1.3 fixture, one-task `$0.15` provider ceiling, artifact-before-cleanup, and no concurrent case. It must pass every applicable hard gate before any promotion; otherwise preserve the artifact, clean the scope, and reject the candidate. Do not start P1/P5, heldout work, or the ten-task concurrency comparison first.

## 2026-10-13 — P0-2 v1.3 routing-repair real trace (evaluation false-negative; P0 remains unapproved)

- Under the user's ongoing per-task `$0.15` provider authorization, submitted exactly one new disposable development task (`92`) through the real API -> Outbox -> Worker path using the frozen East document, ACME read-only demo source, and `deepseek-chat`. The persisted artifact is `backend/.evaluation-runs/p0-2-document-finding-v1-3-r2/evaluation/run.json`; it was evaluated before cleanup. The task completed in 75,439 ms with four provider calls (Planner, semantic review, Knowledge, Reviewer), 5,070 tokens, and settled cost `$0.001988`, all within the frozen four-call, 8,000-token, and `$0.15` limits.
- The routing repair worked in the real Worker: persisted route `knowledge_only`, intent `document_question`, one ready knowledge result, one frozen document path and chunk citation, semantic verdict `supported`, completed report, deterministic validation, citation validation, report persistence, and security checks all passed. The real answer identified CUST-0001, its contract expiry, and the CRM/business record of paused ordinary procurement; the source-bound qualification correctly retained the non-unique-cause boundary.
- The automatic evaluator nevertheless rejected only `required_claims_supported`. This is a deterministic evaluator false-negative, not evidence of an unsupported answer: fixture v1.3 requires the contiguous literal `暂停采购`, while the frozen source and returned supported claim say `暂停常规采购`. The latter is the source's more specific form and directly supports the former question. The evaluator currently uses raw substring matching, so it cannot recognize this documented modifier without a new, auditable matching rule. The fixture and source were not changed after observing the result.
- After the artifact was retained, cleanup used only the manifest-recorded disposable IDs. Post-cleanup database checks returned zero rows for task `92`, company `34`, document `21`, user `42`, data source `27`, and schema snapshot `27`; readiness remained `database=ok`, `redis=ok`, `object_storage=ok`, and `task_capacity=ok`.

### Automatic audit decision

- **Reject this candidate result as a hard-gate pass; P0-2/P0 remain unapproved.** The runtime routing defect is repaired, but the evaluation contract is not yet sound enough to make a promotion decision. The next permitted no-cost slice is to define and test a bounded, negation-safe deterministic term-variant rule for frozen document claims (or to reject that approach with evidence). It must not relax unrelated claim matching, alter v1.3 after the run, use an LLM judge, or create another provider request. Only after that rule and regression suite are audited may the retained task-92 artifact be re-evaluated; a new paid task is needed only if source/runtime behavior changes.

## 2026-10-13 — P0-2 deterministic document-claim term contract and task-92 replay (candidate evidence only)

- Added a narrowly scoped deterministic document-claim matcher. It permits only the explicitly entailing action-object variants `暂停常规采购` / `暂停日常采购` / `暂停例行采购` for the frozen expectation `暂停采购`; it does not add fuzzy matching or alter any other term. It rejects a match where the immediate preceding context carries a negation marker. This logic applies only to supporting claims: source qualifications and limitations retain their literal term semantics, so `不能只归因` remains a valid qualification rather than being misclassified as a negated claim.
- Red/green regressions prove three boundaries: the frozen-source phrase `暂停常规采购` supports the broader claim; an unapproved phrase `暂停非采购` does not; and `没有暂停采购` does not satisfy the positive claim. The first implementation incorrectly applied negation filtering to qualifications, and the existing `不能只归因` test caught that regression before it could pass; the final boundary applies negation rejection only to support claims.
- Verification: focused evaluation/planner/workflow suite `80 passed`; relevant analysis/workflow/reporting/evaluation suite `338 passed, 4 skipped`; Ruff passed and formatting was applied to the changed evaluation test; `git diff --check` passed with only pre-existing whole-workspace line-ending warnings. No provider model request, task, tenant, document upload, or heldout case was created.
- The retained task-92 `run.json` was re-evaluated inside the evaluation container against unchanged v1.3 fixture data and its persisted observation. `re_evaluation_after_term_contract.json` records `passed=true`, `hard_gate_status=passed`, no violations, and no unknown checks. This replay created zero model calls; it validates the evaluator correction against the unchanged runtime output, not a new runtime execution.

### Automatic audit decision

- **Approve only the deterministic evaluation-contract correction and the single task-92 replay as candidate evidence. P0-2/P0 remain unapproved.** The runtime code has not changed since task 92, but one development case and one model execution do not prove the other three document cases, heldout behavior, recovery, or concurrency. The next permitted step is a bounded review of the remaining v1.3 development cases and their source-specific contracts before spending further provider budget; do not promote to baseline, begin P1/P5, use heldout data, or start the ten-task concurrency comparison.

## 2026-10-13 — P0-2 remaining document-contract source audit and v1.4 development fixture (preflight only)

- Source audit of the three unrun v1.3 cases confirms that the quality source explicitly states `SUP-003` + `传感器` + `稳定性异常`, and the receivable source explicitly supports `CUST-0280` + `回款风险` + `催收`; both narrow support questions remain complete answers at their stated scope. No provider call was made.
- The margin source exposed a second frozen-contract defect before it could consume budget: its conclusion says `文档不支持只归因于其中任一因素`, while v1.3 requires the literal pair `不能` + `只归因`. The runtime source-bound-qualification filter requires verbatim source content, so this v1.3 expectation cannot be reliably satisfied by a correct source-bound answer. This is a fixture defect, not a reason to weaken source validation or force model wording.
- v1.3 remains unchanged because task 92 already used it. Added development-only `business-knowledge-development-v1.4` with the same cases, scopes, routes, budgets, and outcomes; its sole semantic correction is the margin qualification pair `不支持` + `只归因`, which appears in the frozen document. Regression first failed while v1.4 did not exist, then passed `33 passed`; Ruff and formatting checks passed; `git diff --check` passed with only pre-existing workspace line-ending warnings.

### Automatic audit decision

- **Approve only the v1.4 source-contract preflight. P0-2/P0 remain unapproved.** The task-92 v1.3 replay is valid evidence for the routing repair, but the unrun cases must now be exercised under immutable v1.4. Because their current runtime code was already exercised after routing repair and the remaining questions use the same narrow document route, the next permitted provider work is one disposable v1.4 task at a time, each capped at `$0.15`, artifact-before-cleanup, and automatic hard-gate audit after every task. Do not use heldout data, concurrency, P1, or P5 first.

## 2026-10-13 — P0-2 v1.4 quality-batch real trace (passed; P0 remains unapproved)

- Submitted exactly one disposable `knowledge-quality-batch-evidence` task (`93`) through the real API -> Outbox -> Worker path using the immutable v1.4 fixture, its single frozen quality-review document, ACME read-only demo source, and `deepseek-chat`. The evaluation artifact is `backend/.evaluation-runs/p0-2-document-finding-v1-4-quality/evaluation/run.json`, created before cleanup.
- The task completed in 5,659 ms with four provider calls, 4,900 tokens, and settled cost `$0.001908` under the per-task `$0.15`, four-call, and 8,000-token caps. Every applicable hard gate passed: `knowledge_only`/`document_question`, one frozen path/chunk citation, supported semantic review, completed persisted report, required `SUP-003`/`传感器`/`异常` support claim, deterministic and citation validation, budget, and security. The source-bound qualifications correctly identify the supplier anomaly as a documented hypothesis rather than a recomputable fact or a conclusion about all products/customers.
- Cleanup was limited to this manifest's disposable scope. Post-cleanup checks returned zero rows for task `93`, company `35`, document `22`, user `43`, data source `28`, and schema snapshot `28`; readiness still reports database, Redis, object storage, and task capacity `ok`.

### Automatic audit decision

- **Approve only this second single-case v1.4 development trace. P0-2/P0 remain unapproved.** Two independently prepared narrow support cases now pass (task-92 replay under the repaired evaluator and task-93 real trace), but the source-bound multi-factor qualification and receivable-risk inputs remain unproved. The next permitted provider work is exactly one disposable `knowledge-margin-two-factors` v1.4 task with the same `$0.15` ceiling and artifact/cleanup audit. Do not begin P1/P5, heldout, or concurrency work.

## 2026-10-13 — P0-2 postposed document-evidence routing contract (candidate preflight; runtime rebuild pending)

- Before spending the permitted margin-case budget, a no-cost probe applied the same bad model output (`business_cause` / `hybrid`) to `传动控制毛利压力有哪些被资料支持的因素？`. The existing narrow recognizer returned `hybrid`, proving that it covered only the initial `哪些资料支持...` grammar and would not protect this equally explicit document-evidence question.
- Added the bounded postposed form `...有哪些被资料/文档支持的因素/事实/结论` to the shared routing boundary. Its red regression first failed; after correction it normalizes to `document_question` / `knowledge_only` and the graph selects `knowledge_node`. The existing causal-question negative remains in the same suite. Verification passed `53` focused Planner/decision/workflow tests and `340 passed, 4 skipped` across analysis/workflow/reporting/evaluation; Ruff, formatting, and `git diff --check` passed with only pre-existing workspace line-ending warnings.
- No provider call, tenant, upload, task, heldout case, P1/P5 work, or concurrency comparison occurred in this repair. An attempt to rebuild API/Worker/report-worker was interrupted by Docker Desktop reporting `unable to start`; the CLI became unavailable before container-image or readiness evidence could be recorded. A controlled Docker Desktop restart was initiated after task-93 cleanup, but the engine had not yet returned to CLI-ready state at the end of this check.

### Automatic audit decision

- **Approve only the static routing-contract preflight. P0-2/P0 remain unapproved and runtime execution is paused on local Docker-engine recovery.** Do not submit the margin task until Docker returns, the Worker image is rebuilt, the shared contract runs inside that Worker without a provider call, and readiness is `ok`. Then the next permitted provider action remains one disposable v1.4 margin task with the `$0.15` ceiling and full artifact/cleanup audit.

## 2026-10-13 — Local Docker engine recovery root cause (external action required)

- Repeated CLI probes blocked before returning a Docker server version. Docker Desktop's own `backend.error.json` identifies the startup boundary: the services component cannot remove the runtime endpoint `C:\Users\qyf21\AppData\Local\Docker\run\dockerInference`, so the backend cancels before the Linux engine becomes available. File inspection identifies it as a zero-byte reparse point last modified before this execution; it is a regenerable IPC endpoint, not a project file, image, volume, or database.
- The project-side route repair and all static verification remain intact, but API/Worker image rebuild and any further real evaluation are unproved while Docker is unavailable. No margin task, provider call, tenant, upload, heldout case, P1/P5 work, or concurrency run was created after task 93.

### Automatic audit decision

- **P0-2/P0 remain paused on the external Docker IPC recovery.** Close Docker Desktop, remove only the stale `dockerInference` endpoint, relaunch Docker Desktop, and wait for `docker version` to return a Server version. This does not authorize a Docker factory reset, WSL distribution reset, data-root deletion, image/volume deletion, or a provider rerun. Once the engine is back, resume the already-audited Worker rebuild and single margin task sequence.

## 2026-10-13 — Docker recovery, P0-2 margin trace, and cleanup (passed; P0 remains unapproved)

- After the user restarted Docker Desktop, `docker version` returned server `29.6.1`; project dependencies and application readiness returned healthy. API, Worker, and report-worker were rebuilt. A no-provider contract executed inside the rebuilt Worker confirmed that the postposed margin question normalizes a bad `hybrid`/`business_cause` plan to `knowledge_only`/`document_question`.
- The first margin preparation attempt created no analysis task and no provider call: Docker restart had left the ACME demo business container stopped, so its host name could not resolve. Its partial manifest was cleaned before retry. After the three business database containers were explicitly started and healthy, the retry submitted exactly one disposable task (`94`) using immutable v1.4 and the frozen margin document.
- Task `94` completed through real API -> Outbox -> Worker execution in 79,732 ms with four provider calls, 5,035 tokens, and settled cost `$0.001998`, below the task's five-call, 10,000-token, and `$0.15` ceilings. Every applicable hard gate passed: protected knowledge-only route, two required source-supported factors, the exact `不支持` + `只归因` source qualification, one frozen path/chunk citation, completed persisted report, deterministic/citation validation, budget, and security. Its artifact is `backend/.evaluation-runs/p0-2-document-finding-v1-4-margin-r2/evaluation/run.json`.
- Cleanup was limited to the retry manifest. Post-cleanup checks returned zero rows for task `94`, company `37`, document `23`, user `45`, data source `30`, and schema snapshot `29`; readiness remains database, Redis, object storage, and task capacity `ok`.

### Automatic audit decision

- **Approve this third single-case v1.4 development trace. P0-2/P0 remain unapproved.** The final unrun v1.4 development input is the receivable-risk support question. Its source contract has been audited and it uses the already-proven initial document-evidence grammar. The next permitted provider action is exactly one disposable `knowledge-receivable-risk-boundary` task with the same `$0.15` ceiling, artifact-before-cleanup, and hard-gate audit. Do not advance to heldout, P1/P5, or concurrency first.

## 2026-10-13 — P0-2 v1.4 receivable trace and development-set aggregate (passed; P0 remains unapproved)

- Submitted exactly one disposable `knowledge-receivable-risk-boundary` task (`95`) through real API -> Outbox -> Worker execution using immutable v1.4, the frozen receivable-risk document, ACME read-only demo source, and `deepseek-chat`. It completed in 5,952 ms with four provider calls, 5,010 tokens, and settled cost `$0.001966`, within its four-call, 8,000-token, and `$0.15` ceilings. Its saved artifact is `backend/.evaluation-runs/p0-2-document-finding-v1-4-receivable/evaluation/run.json`.
- Every applicable hard gate passed: `knowledge_only` / `document_question`, required CUST-0280 risk-and-collection support, one frozen path/chunk citation, completed persisted report, deterministic and citation validation, budget, and security. The response retained the source boundary that overdue payment does not itself establish bad debt.
- Manifest-limited cleanup returned zero rows for task `95`, company `38`, document `24`, user `46`, data source `31`, and schema snapshot `30`; post-cleanup readiness remains database, Redis, object storage, and task capacity `ok`.
- A zero-provider-call evaluation-container replay combined the four persisted real Worker observations: task-92 East-contract observation under the unchanged v1.4 first-case contract, plus tasks 93/94/95. `backend/.evaluation-runs/p0-2-document-finding-v1-4-development-aggregate.json` records 4/4 hard-gate pass, route/citation/claim/outcome/publication rates of 1.0, zero security incidents, 16 provider calls, 20,015 tokens, and `$0.007860` settled cost. Each source artifact remains independently retained; the aggregate did not create another task or conceal cross-run execution.

### Automatic audit decision

- **Approve the P0-2 v1.4 document-route development-set evidence only. P0 remains unapproved.** This proves the repaired narrow document-only slice on four development cases, not heldout generalization, data/hybrid correctness, denial/recovery behavior, concurrency, or production scale. The next P0 action is a read-only roadmap/evidence audit to identify the earliest unmet P0 gate and its required baseline/candidate contract; do not label P0 complete, promote a default, start P1/P5, or run the ten-task concurrency comparison yet.

## 2026-10-13 — P0-2 heldout no-evidence evaluation (candidate rejected)

- The preparation harness now requires explicit `--heldout-evaluation` and accepts only selected heldout cases under that flag; default preparation still refuses heldout input and mixed development/heldout selection is rejected. Its focused regression/evaluation suite passed `54 passed`; Ruff, format, and scoped diff checks passed. This changes only evaluation admission, not Gold, Planner, report logic, or model configuration.
- The one frozen heldout case `knowledge-heldout-no-evidence` ran once as task `96` through the real API -> Outbox -> Worker path with the server-owned `$0.15` cap. The frozen artifact is `backend/.evaluation-runs/p0-heldout-run/evaluation/run.json`. It made five settled calls, used 8,333 tokens, cost `$0.003317`, and had zero security incidents. It failed hard gates for route, outcome, limitation, and budget: the persisted route was `hybrid` / `business_cause`, outcome was `partial`, and the case budget is four calls / 8,000 tokens.
- Cleanup used only the run manifest. Post-cleanup checks returned zero rows for task `96`, company `40`, user `48`, data source `33`, and schema snapshot `31`; readiness remained fully `ok`.

### Automatic audit decision

- **Reject the document-route candidate for P0-2. P0 remains unapproved.** Four development passes do not generalize to the frozen no-evidence route. Preserve this heldout failure as a Bad Case; do not tune the current Planner against it, rerun it, promote the candidate, start P1/P5, or begin the concurrency comparison. The next action is a no-cost architecture review that separates the shared explicit-document grammar from a no-evidence stop condition using development-only evidence before any new paid evaluation.

## 2026-10-13 — P0-2 heldout failure architecture review (no candidate change)

- Current source trace is `planner_node` / `planner_semantic_review_node` -> `enforce_explicit_document_evidence_contract` -> graph route. The guard only recognizes two fixed word orders. A non-matching model `business_cause` / `hybrid` plan therefore reaches Data before Knowledge. Once Knowledge is reached, `KnowledgeAgent` already maps zero retrieval evidence to `insufficient_evidence`, and `choose_next_action` already stops a knowledge-only insufficient route without retry. The failure is upstream route admission, not RAG's empty-evidence handling or Router termination.
- A blanket `document_ids=[] -> insufficient_evidence` rule is rejected: ordinary `data_only` questions legitimately have no document scope. A model-only `intent.kind` rule is also insufficient because the heldout observation proves the model can return the wrong kind. Adding the observed heldout word order to the regex or Planner prompt is prohibited because it would tune directly to frozen holdout input.

### Automatic audit decision

- **No runtime candidate is admitted.** The next P0-2 design must derive a server-owned, testable document-evidence request contract from independent development requirements before it can select a knowledge-only/no-evidence stop path. Until that contract has development-only boundary cases, containment tests, and a rollback path, no provider call, heldout rerun, candidate promotion, P1/P5 work, or concurrency comparison is permitted.

## 2026-10-13 — P0-2 development-only document-evidence grammar candidate (static preflight)

- The contract is derived from existing development requests that use the explicit `资料支持` marker, not from the heldout wording. The shared Planner guard now recognizes that marker wherever it appears in a question, while retaining the existing `被资料支持` form. It still acts only on `analyze` decisions and preserves a pure causal question without an explicit document-support marker as `hybrid`.
- A new regression uses the distinct development question `请列出资料支持SUP-003传感器批次异常的依据。`; its intentionally bad model `business_cause` / `hybrid` output is normalized to `document_question` / `knowledge_only` before graph routing. The red regression failed against the prior source. After the one-line shared-boundary change, Planner, schema, Workflow and Router verification passed `67 passed`; changed-file Ruff and format checks passed. Scoped diff checking found no whitespace error (only established CRLF conversion warnings).

### Automatic audit decision

- **Approve only this static development candidate. P0-2 remains unapproved.** It does not prove a real Worker result, no-evidence terminal outcome, cost/call budget, or heldout generalization. The next permitted provider action is one disposable development-only task using this distinct question and the existing frozen SUP-003 document, capped at `$0.15`, with artifact-before-cleanup and automatic hard-gate review. Do not rerun the heldout case or start P1/P5/concurrency first.

## 2026-10-13 — P0-2 v1.5 prefixed document-evidence development trace (passed; P0 remains unapproved)

- Under the user's standing per-task `$0.15` authorization, submitted exactly one disposable development task (`97`) through the real API -> Outbox -> Worker path using immutable `business-knowledge-development-v1.5`, the frozen SUP-003 quality-review document, the ACME read-only demo source, and `deepseek-chat`. The saved evaluation artifact is `backend/.evaluation-runs/p0-v15-run-r2/evaluation/run.json`, created before cleanup.
- The real Worker persisted `knowledge_only` / `document_question`, one frozen document path and one chunk citation, ready knowledge evidence, semantic verdict `supported`, a completed report, and passed deterministic, citation, numeric, budget, report-persistence, and security checks. Every applicable evaluator hard gate passed. It used four provider calls, 5,034 tokens, 99,149 ms, and settled `$0.002000`, within the frozen four-call, 8,000-token, and `$0.15` limits.
- Cleanup used only the manifest-recorded disposable scope. The first reverse query named a non-existent table (`data_sources`), so it was not treated as evidence. A corrected read-only check against the actual schema returned zero rows for task `97`, company `42`, user `50`, business data source `35`, schema snapshot `33`, and document `26`; readiness then returned database, Redis, object storage, and task capacity all `ok`.

### Automatic audit decision

- **Approve only this v1.5 development trace and its cleanup evidence. P0-2/P0 remain unapproved.** This confirms the development-derived prefixed grammar is correctly contained in the real Worker, but it does not change the already rejected frozen no-evidence result, prove the no-evidence terminal contract, or permit a heldout rerun. The next legal P0-2 work is no-cost: derive and review a development-only no-evidence request/terminal contract with boundary and rollback tests. Do not start P1/P5 or the concurrency comparison first.

## 2026-10-13 — P0-2 knowledge-only no-evidence lifecycle contract (runtime preflight; no paid task)

- The heldout failure analysis exposed two independent lifecycle defects without reusing its wording: a `knowledge_only` result with no evidence reached the bounded router as `non_retryable_or_unknown_failure`, and the evaluation adapter inferred its analysis outcome from the task's persisted `partial` status. The latter conflates task lifecycle/publication with the analysis result.
- The smallest shared-boundary repair keeps the existing Knowledge -> Reviewer/Composer -> deterministic validation -> persistence chain. When a protected `knowledge_only` route returns `insufficient_evidence`, the router now records the explicit terminal analysis outcome `insufficient_evidence`; the task may still remain `partial` if its report is partial. The observation adapter recognizes only this explicit workflow terminal outcome, rather than generally reinterpreting all partial tasks. Reviewer semantic-model review is skipped only when both data and document evidence lists are empty; Composer and deterministic validation still run.
- Red regressions first proved the old router returned `non_retryable_or_unknown_failure` and the old observation returned `partial`. Green verification then passed `59` focused workflow, worker-persistence, Reviewer/Composer, and evaluation-observation tests; selected Ruff passed and all changed production/test files except the pre-existing long-layout portion of `test_workflow_router.py` passed format check. Scoped `git diff --check` found no whitespace error apart from the workspace-wide pre-existing CRLF conversion warnings.
- API, Worker, and report-worker were rebuilt. A no-provider assertion inside the rebuilt Worker produced `worker-insufficient-evidence-contract-ok`; readiness reports database, Redis, object storage, and task capacity all `ok`. No tenant, document, task, heldout evaluation, or provider call was created.

### Automatic audit decision

- **Approve only this no-evidence lifecycle/runtime preflight. P0-2/P0 remain unapproved.** The next permitted provider action is exactly one new, development-only, empty-document-scope case derived from the explicit `资料支持` contract, with a `$0.15` ceiling, artifact-before-cleanup, and full hard-gate audit. It must prove the actual Worker route, zero document evidence, `insufficient_evidence` analysis outcome, partial-report publication boundary, model/cost budget, and cleanup. Do not rerun the frozen heldout case or start P1/P5/concurrency first.

## 2026-10-13 — P0-2 v1.6 empty-document-scope trace (hard-gate unknown; candidate not approved)

- One distinct development-only empty-scope task (`98`) ran through the real API -> Outbox -> Worker path under the `$0.15` cap. Its artifact is `backend/.evaluation-runs/p0-v16-run/evaluation/run.json`. The corrected route and lifecycle behavior appeared in production code: `knowledge_only` / `document_question`, zero document evidence and citations, no Reviewer semantic-review result, persisted analysis outcome `insufficient_evidence`, a persisted partial report, two provider calls, 3,305 tokens, 57,062 ms, and settled `$0.001218`. Route, outcome, limitation, budget, persistence, and security checks passed.
- The evaluator correctly refused to promote it: citation validation and deterministic validation were `unknown`, so the run hard-gate result was `unknown`, not pass. Root cause is local and reproducible: the empty-evidence Reviewer branch skipped the semantic model as intended, but also omitted the existing deterministic final-answer validator. The report itself was schema-validated by persistence, but the independent schema/numeric/citation checks were not recorded, so no evidence permits treating them as passed.
- Cleanup was limited to the manifest-recorded disposable scope. A corrected direct check returned zero rows for task `98`, company `43`, user `51`, business data source `36`, and schema snapshot `34`; readiness remained database, Redis, object storage, and task capacity `ok`.

### Automatic audit decision

- **Reject the v1.6 runtime candidate as incomplete evidence; P0-2/P0 remain unapproved.** Preserve its artifact; do not relabel unknown checks as passed, touch the frozen heldout case, or start P1/P5/concurrency. The next permitted no-cost candidate is to reuse the existing deterministic final-answer validator in the empty-evidence Reviewer branch, with a red regression proving all three checks are recorded. After static tests and rebuilt-Worker verification, one new candidate replay of the same immutable development case may compare the implementation change under the same `$0.15` ceiling.

## 2026-10-13 — P0-2 v1.6 empty-document-scope validation replay (passed; P0 remains unapproved)

- The v1.6 hard-gate-unknown artifact is retained as the candidate baseline. Its root-cause repair reused the existing `_validate_final_answer` in the empty-evidence Reviewer branch. It does not invoke a model, weaken citation/number/schema rules, or alter Planner/RAG behavior; it records the schema, numeric, and citation outcomes that the already-rendered partial answer must satisfy. Red regression first proved `answer_validation` was absent; after the change, `106` focused Reviewer/Composer, router, Worker persistence, observation, fixture, and preparation tests passed. Selected Ruff, format checks, and scoped diff checks passed (the workspace still emits established CRLF conversion warnings).
- API, Worker, and report-worker were rebuilt. A no-provider Worker assertion printed `worker-empty-evidence-validation-contract-ok`, confirming that semantic review remains skipped only for empty evidence while all three deterministic checks are true. Readiness returned database, Redis, object storage, and task capacity `ok`.
- One new candidate replay (`99`) used the same immutable v1.6 development case and no document scope, with the same server-owned `$0.15` ceiling. The saved artifact is `backend/.evaluation-runs/p0-v16-r2-run/evaluation/run.json`. All applicable hard gates passed: `knowledge_only` / `document_question`, zero document evidence/citations, explicit `insufficient_evidence` analysis outcome, required no-evidence limitation, partial-report persistence boundary, deterministic/numeric/citation validation, budget, and security. It used two provider calls, 3,307 tokens, 140,036 ms, and `$0.001221`; the longer duration is the one-time rebuilt-container local embedding-model download/load, while the paid call count remained two.
- Manifest-limited cleanup returned zero rows for task `99`, company `44`, user `52`, business data source `37`, and schema snapshot `35`; readiness stayed fully `ok`.

### Automatic audit decision

- **Approve this v1.6 no-evidence development candidate and its before/after evidence only. P0-2/P0 remain unapproved.** The repaired slice now covers both a source-supported document answer and one empty-document explicit-evidence request, but it does not erase the frozen heldout failure, establish broader document grammar generalization, validate data/hybrid paths, or prove recovery/concurrency. The next P0 action is a read-only gate audit: identify the earliest remaining development-only P0-2 contract or an independently designed no-evidence boundary before authorizing any further provider run. Do not rerun frozen heldout data, start P1/P5, or start the ten-task concurrency comparison.

## 2026-10-13 — P0-2 hybrid insufficient-evidence development trace (rejected; evaluation contract gap found)

- One disposable frozen-development task (`100`, `insufficient-new-product-cause`) ran through the real API -> Outbox -> Worker path against the ACME read-only demo source with empty document scope and the server-owned `$0.15` cap. Its retained artifacts are `backend/.evaluation-runs/p0-hybrid-insufficient-run/run.json`, `report.md`, `trace.md`, and `prepare.json`. The actual plan was `hybrid` / `business_cause` with `entities=["某新产品"]` and `period="2024-03"`; its terminal analysis outcome was `insufficient_evidence`, task lifecycle status remained `partial`, the report persisted, there were zero security incidents, four provider calls, 7,134 tokens, 69,400 ms, and settled cost `$0.002799`.
- The trace was rejected, not promoted: before the repair, the shared Reviewer data-insufficient branch returned before invoking deterministic final-answer validation, so persisted schema/numeric/citation checks were `unknown`; its persisted limitation also omitted the required document-evidence boundary. The artifact was copied before cleanup. Manifest-limited cleanup returned zero rows for task `100`, company `45`, user `53`, data source `38`, and schema snapshot `36`; readiness remained database, Redis, object storage, and task capacity `ok`.
- The root-cause repair is shared rather than case-specific. Planner semantic review now asks for all nine `PlannerDecision` fields and preserves an existing `evaluation_scope` if a rewritten analyze plan omits it. For any `hybrid` result where both Data and Knowledge are `insufficient_evidence`, Reviewer now persists the document-evidence limitation and applies the existing deterministic final-answer validator. Focused verification passed `125` tests; Ruff and scoped diff checks passed. This repair has static and rebuilt-source coverage, but no post-repair provider replay was admitted yet.
- The no-replay decision is evidence-based: Gold currently stores semantic values such as `{"scenario":"new_product_cause"}` in `expected_result_fingerprint`, while the persisted Observation intentionally stores only a SHA-256 of validated SQL rows. For this no-matching-records path the implementation intentionally returns no SQL-row fingerprint. The evaluator compares those values literally, and its schema forbids marking SQL gates inapplicable for `hybrid` routes. Therefore this frozen case cannot pass all current hard gates by construction; changing its expected value after observing task `100` would be evaluation tuning, and rerunning it would not close the gap.
- An independent read-only query against the ACME demo business database confirmed `products.name ILIKE '%某新产品%'` returns `0`; this establishes the intended empty-product premise independently of task `100`, but does not turn its semantic Gold label into an executable SQL-row fingerprint.

### Automatic audit decision

- **Reject task `100` as a P0-2 candidate and retain it as a Bad Case. P0-2/P0 remain unapproved.** Do not rerun this development case, the frozen heldout case, or begin P1/P5/concurrency. The next permitted work is no-cost: version an independently derived result-fingerprint contract that can distinguish validated SQL rows from an explicit no-matching-records result, then add deterministic evaluator and persistence tests before any new provider task is admitted.

## 2026-10-13 — P0-2 no-matching-records fingerprint contract (static preflight)

- The shared fingerprint builder now accepts exactly one additional provable state: `data_result.status=insufficient_evidence` together with `error_code=no_matching_records`. It hashes the canonical status/error-code pair, preserving the existing SHA-256 format; all other insufficient, failed, or malformed data states still return no fingerprint. This represents a validated empty SQL result, not a model rationale or a synthetic business fact.
- The independent ACME read-only database check establishes that the searched product name has zero matching `products.name` rows. Focused fingerprint, Worker terminal persistence, observation, evaluator, Reviewer, and Planner semantic-review checks passed `85` tests; selected Ruff, format, and scoped diff checks passed. Gold v1 and every heldout case remain unchanged.

### Automatic audit decision

- **Approve only the static no-matching fingerprint contract. P0-2/P0 remain unapproved.** Before another provider task, create a versioned development fixture whose expected value is the independently derived no-matching fingerprint and whose policy explicitly records why row, numeric, and citation checks apply or do not apply. Do not modify Gold v1, rerun task `100`, touch heldout, or begin P1/P5/concurrency.

## 2026-10-13 — P0-2 v2 hybrid no-match attempt and terminal-state repair (candidate rejected)

- The isolated `business-hybrid-insufficient-development-v2` fixture passed static evaluator/preparation checks, then one fresh disposable development task (`101`) ran under the `$0.15` cap. It ended `needs_clarification`, with no persisted plan/report/route observation, six provider calls, 10,497 tokens, and settled `$0.004033`; it therefore failed route, outcome, publication, and its five-call budget. `backend/.evaluation-runs/p0-hybrid-v2-run/run.json` is retained. Manifest cleanup returned zero rows for task `101` and company `46`; readiness remained fully `ok`.
- Source inspection then found a separate terminal-state defect: a durable `NodeOutcome.no_matching_records` stops the Router as intended, but its stop reason was not mapped to the explicit `insufficient_evidence` analysis outcome. The shared Router mapping now includes `no_matching_records`; focused router, Worker terminal persistence, Observation, and fingerprint tests passed `43` cases. API, Worker, and report-worker were rebuilt, and a no-provider assertion in Worker printed `worker-no-match-terminal-contract-ok` with readiness `ok`.

### Automatic audit decision

- **Reject v2 task `101`; approve only the no-match terminal-state repair. P0-2/P0 remain unapproved.** Do not rerun task `101`, modify Gold v1, use heldout, or begin P1/P5/concurrency. Before any new provider task, extend the harness procedure to preserve the full task trace before cleanup, then use that trace to distinguish a legitimate one-time scope clarification from a Planner/semantic-review regression.

## 2026-10-13 — P0-2 cleanup trace retention (static harness verification)

- Evaluation cleanup now renders every manifest-listed terminal task through the existing tenant-scoped, metadata-only trace renderer before deleting it. The generated `traces/task-<id>.html` path is recorded in the manifest; a trace-rendering failure prevents destructive cleanup. No model call, database write outside the disposable test scope, or new dependency was added.
- The terminal-task cleanup regression proved the saved HTML includes task audit metadata but excludes the private task question, then verified the task and disposable tenant resources are removed. Harness and trace tests passed `14`; Ruff, format, and scoped diff checks passed.

### Automatic audit decision

- **Approve this static trace-retention harness repair only. P0-2/P0 remain unapproved.** Rebuild the Worker before any later real evaluation so the updated harness is available. The next provider admission still requires a distinct development contract and preflight; do not rerun task `101`, modify Gold v1, use heldout, or start P1/P5/concurrency.

## 2026-10-13 — P0-2 data-only no-match v3 trace and clarification observability repair

- The distinct development-only fixture `business-data-no-match-development-v3` was derived from an independent ACME read-only check: `regions.name='不存在的测试区域'` returns `0`. Its expected value is the existing canonical `no_matching_records` SHA-256 fingerprint, with `data_only`, no document scope, `insufficient_evidence`, and a no-fabricated-number limitation. Static evaluator, fingerprint, Router, Reviewer, and cleanup-harness verification passed `85` tests; the fixture JSON was separately parsed because the Python formatter's suggested trailing-comma form is not valid JSON.
- One disposable real task (`102`) ran through API -> Outbox -> Worker with the `$0.15` cap. It stopped at `needs_clarification` after Planner plus two semantic-review calls: 3 calls, 5,065 tokens, 9,758 ms, and `$0.001842`. Its retained evaluator artifact is `backend/.evaluation-runs/p0-data-no-match-v3-run/evaluation/run.json`; it failed route, outcome, limitation, report-persistence, and the dependent unknown hard gates. It made no SQL or local-resource call and had no security incident. This is a rejected development trace, not evidence that the no-match data path works end to end.
- Cleanup rendered `prepared/traces/task-102.html` before deletion, then removed task `102`, company `47`, user `55`, data source `40`, and snapshot `38` (all post-cleanup counts `0`); readiness remained database, Redis, object storage, and task capacity `ok`. The trace proves the exact node chronology `Planner -> semantic review -> needs_clarification`, but correctly excludes model output and task content, so it cannot establish why that semantic decision was made.
- Source review found a concrete observability break rather than a basis to tune the Planner: `planner_terminal_node` rendered `ClarificationSpec.missing_slots` to user text but omitted the bounded slot list from `terminal_result`; task persistence therefore could not fill `clarification_missing_fields`. The minimal repair propagates only existing allowlisted slots and the privacy-safe trace renders only those fields. It does not expose question text, prompts, SQL, tool payloads, model free text, or report bodies. Relevant tests passed `103`; Ruff, format, and scoped diff checks passed. Worker was rebuilt and a no-provider in-container assertion confirmed terminal persistence data and trace redaction; readiness is `ok`.

### Automatic audit decision

- **Reject task `102`; approve only the clarification-state/trace observability repair. P0-2/P0 remain unapproved.** The new repair was not present during task `102`, and task `102` did not exercise Data or the no-match terminal path. Do not rerun task `102`, alter Gold v1, reuse heldout input, start P1/P5, or begin the concurrency comparison. The next permitted work is a no-cost review to select an unused development-only clarification contract whose expected slots can be independently specified; only after its static/preflight gate passes may one bounded real task test persisted clarification fields and the trace.

## 2026-10-13 — P0-2 clarification terminal v4 trace (passed; P0 remains unapproved)

- The prior gate review found that a genuine `needs_clarification` terminal could not pass the ordinary analysis evaluator: it has no resolved business scope, SQL fingerprint, report, numeric validation, or citation validation. Treating those absent artifacts as unknown is correct for a business analysis, but incorrect for a terminal whose contract is explicitly to stop before any business tool. This is an evaluation-model defect, not a reason to mark those checks passed.
- Added the narrow `clarification` evaluation kind. It requires a null route, `needs_clarification` outcome, exact allowlisted missing slots, no governed tool call/report publication, budget, and security; the intentionally inapplicable business-result checks remain `null` and are excluded from business-analysis quality rates. The persisted-task adapter now reads and validates `clarification_missing_fields`, and derives no-side-effects/security evidence only for this zero-tool terminal. Preparation and CLI task-map handling accept this type; security-rejection handling is unchanged.
- The independent development-only fixture `business-clarification-development-v4` uses `华东区销售额是多少？`: metric and region are present, while the required time range is not. Static fixture parsing and `107` focused evaluation/observation/CLI/preparation/workflow/trace tests passed; Ruff, formatting, and scoped diff checks passed. Worker was rebuilt, a no-provider assertion passed, and readiness was fully `ok`.
- One disposable task (`103`) then ran through the real API -> Outbox -> Worker path under the `$0.15` ceiling. Its saved artifact is `backend/.evaluation-runs/p0-clarification-v4-run/evaluation/run.json`. It reached `needs_clarification` in 7,271 ms with three provider calls, 4,711 tokens, and `$0.001674`. It persisted exactly `clarification_missing_fields=["time_range"]`, had null route, zero tool calls, no report publication, no security incident, and every applicable clarification hard gate passed. The trace retains the same safe fields without task text or model output.
- Manifest-limited cleanup preserved `prepared/traces/task-103.html` before deleting task `103`, company `48`, user `56`, data source `41`, and snapshot `39`; all post-cleanup counts are zero and readiness remains database, Redis, object storage, and task capacity `ok`.

### Automatic audit decision

- **Approve the v4 clarification-terminal slice only. P0-2/P0 remain unapproved.** It proves a valid pre-analysis stop, not data/no-match behavior or business-answer quality. The next permitted P0-2 work is an independently derived data-only no-match development contract using a known region and an independently verified empty time window; it must complete static/preflight checks before one bounded real task. Do not rerun task `102`, modify Gold v1, use heldout, or start P1/P5/concurrency.

## 2026-10-13 — P0-2 known-region empty-window v5 trace (rejected; false-completion repair)

- A read-only ACME query established that `customers.region_code='EAST'` exists, delivered sales orders span `2024-01-01` through `2025-12-26`, and the same controlled customer/order join for `2020-01` returns exactly `0` rows. This removes the unknown-region variable present in task `102`. The development-only v5 fixture uses `华东区2020年1月销售额是多少？`, expects `data_only`, the canonical no-matching fingerprint, and `insufficient_evidence`; Gold and heldout inputs are unchanged.
- Static fixture parsing plus `144` focused evaluation, fingerprint, Router, Reviewer, preparation, workflow, and trace tests passed; Ruff, format, and scoped diff checks passed. A rebuilt Worker passed the no-provider `no_matching_records -> insufficient_evidence` assertion, and readiness was fully `ok`.
- One fresh disposable v5 task (`104`) reached the real Data node, proving it did not repeat task `102`'s premature clarification. It then ended with four calls, 6,779 tokens, 5,396 ms, and `$0.002521` under the `$0.15`, four-call, and 8,000-token caps. Its artifact is `backend/.evaluation-runs/p0-data-no-match-v5-run/evaluation/run.json`. The persisted route was correctly `data_only`, but Data returned `metric_contract_insufficient` without SQL evidence; Reviewer rendered a failed report and the pre-repair Router recorded `completed`. The evaluator correctly rejected it for outcome, entity, fingerprint, numeric, citation, and deterministic-validation gates. This is not evidence of a no-match query result.
- The failure exposed a separate shared status-machine bug: `data_node` represents a non-retryable metric-contract failure as `NodeOutcome.denied`, `choose_next_action` returns `data_denied`, but `smart_router_node` previously defaulted every non-insufficiency stop to `completed`. The narrow repair maps `*_denied` and `non_retryable_or_unknown_failure` to terminal `failed`; it does not convert them into `insufficient_evidence`, retry an unvalidated SQL candidate, or weaken the metric catalog. Relevant Router/Worker/publication/evaluation tests passed `164`; the rebuilt Worker printed `worker-data-denied-terminal-contract-ok` and readiness remained `ok`.
- Manifest cleanup retained `prepared/traces/task-104.html`, then deleted task `104`, company `49`, user `57`, data source `42`, and snapshot `40`; all post-cleanup counts are zero.

### Automatic audit decision

- **Reject task `104`; approve only the false-completion terminal-state repair. P0-2/P0 remain unapproved.** `metric_contract_insufficient` shows the model candidate did not meet the already-required metric contract; it is not proof that the verified empty window should return zero or that the data route is safe to promote. Do not rerun task `104`, change v5 expectations, modify Gold/heldout, or start P1/P5/concurrency. The next permitted work is a no-cost source and prompt-contract review of the existing sales-revenue metric requirements, followed by a deterministic candidate test before any new paid development run.

## 2026-10-13 — P0-2 revenue-contract repair and null-aggregate v6 trace (rejected)

- The required no-cost review found two shared Data-path gaps. The SQL-generation prompt exposed a metric name, unit, and time column, but not the registered aggregate or fixed filter that the deterministic metric validator requires. Also, a first `metric_contract_insufficient` candidate returned immediately instead of using the existing bounded second candidate-generation attempt. The repair exposes `SUM(sales_orders.total_amount)` and `sales_orders.status = delivered` from the source-controlled metric catalogue and routes a rejected first candidate through one fresh, non-executing repair generation; an unvalidated SQL string is never replayed.
- Static regression covered a rejected first SQL candidate followed by a valid empty-result candidate, prompt content, metric validation, Router, evaluation, observation, fingerprint, Reviewer, preparation, and trace handling: `163 passed`. Changed-file Ruff and scoped diff checks passed; the established CRLF conversion warnings remain. A rebuilt Worker printed `worker-metric-contract-prompt-ok` and then, after the later NULL repair, `worker-null-aggregate-contract-ok`; readiness was database, Redis, object storage, and task capacity `ok`.
- Independent read-only ACME data check confirmed the controlled EAST/delivered order join has `0` rows for `2020-02`. One distinct development-only v6 task (`105`) then ran under the server-owned `$0.15` cap. Its frozen artifact is `backend/.evaluation-runs/p0-data-no-match-v6-run/evaluation/run.json`; it made five provider calls, 8,251 tokens, took 9,495 ms, and settled `$0.003032`, within its six-call and 12,000-token limits with no security incident.
- Task `105` proves the prompt/metric candidate was valid and executed exactly once, but it did **not** prove the intended no-match terminal: PostgreSQL returned one aggregate row `[NULL]` for an empty `SUM`, and the old result validator recognized only `rows=[]`. It incorrectly marked that row as supported evidence; the task ended `partial`, terminal outcome `completed`, and persisted a partial report. The evaluator therefore failed entity, SQL-equivalence, outcome, and limitation gates. This is retained as a Bad Case, not a no-match success.
- The narrow follow-up repair classifies exactly one aggregate result row whose values are all `NULL` as `no_matching_records`, after verifying row shape and expected columns. It leaves a true numeric zero and record-shaped NULL fields as supported observations. The cleanup harness preserved `prepared/traces/task-105.html`, then removed task `105`, company `50`, user `58`, data source `43`, and schema snapshot `41` (all post-cleanup counts `0`); readiness remained fully `ok`.

### Automatic audit decision

- **Reject v6 as runtime evidence; approve only the bounded prompt/retry and NULL-aggregate static/runtime preflight repairs. P0-2/P0 remain unapproved.** Do not rerun task `105`, alter v6, Gold, or heldout input, or begin P1/P5/concurrency. The next permitted provider action is one new development-only empty-month task with a different frozen question, only after its fixture and evaluator preflight pass; it must prove the real `SUM(NULL) -> no_matching_records -> insufficient_evidence` terminal chain, deterministic validation, artifact-before-cleanup, and budget/security gates.

## 2026-10-13 — P0-2 null-aggregate v7 terminal trace (functional path proved; P0 remains unapproved)

- A second independent read-only ACME query confirmed the controlled EAST/delivered order join has `0` rows for `2020-03`. The distinct v7 question was `华东区2020年3月销售额是多少？`; it preserved the canonical no-matching SHA-256, a data-only route, no document scope, `insufficient_evidence`, six-call/12,000-token limits, and the `$0.15` server ceiling.
- Disposable task `106` ran once through API -> Outbox -> Worker. The persisted SQL uses the registered revenue aggregate, delivered filter, region join, and business date filter; its database result is the PostgreSQL aggregate row `[NULL]`. After the shared result-validator repair, Data persisted `status=insufficient_evidence`, `error_code=no_matching_records`, and a `no_matching_records` result assessment; Router persisted terminal `outcome=insufficient_evidence`; Reviewer persisted only the `data_empty` limitation and no confirmed fact or recommendation. Deterministic, numeric, citation, budget, report-persistence, and security checks were all recorded as passed. It made four provider calls, used 6,831 tokens, took 8,081 ms, and settled `$0.002541` with zero security incidents. The original pre-alias evaluator artifact is retained at `backend/.evaluation-runs/p0-data-no-match-v7-run/evaluation/run.json`.
- That original artifact had exactly one evaluator violation: its expected registered region label was `华东` and the persisted Planner scope was the equivalent catalog phrase `华东区`. The runtime SQL, snapshot, and authorization scope are unchanged; literal evaluation did not affect execution. The evaluator now canonicalizes only the optional `区` suffix of names already registered in `customers.region_code`; unrelated values such as `西区` are unchanged. The v7 evaluation regression supplies the exact persisted route, `华东区`, period, fingerprint, outcome, limitation, four calls, 6,831 tokens, 8,081 ms, and `$0.002541`, and passes under the revised contract. Focused evaluation, result, Router, observation, Reviewer, preparation, trace, and CLI verification passed `163`; changed-file Ruff and scoped diff checks passed. The rebuilt Worker printed `worker-region-scope-contract-ok` and readiness remained fully `ok`.
- Cleanup rendered `prepared/traces/task-106.html`, then removed task `106`, company `51`, user `59`, data source `44`, and schema snapshot `42`; all post-cleanup counts are `0`. A later zero-cost CLI reevaluation attempt correctly refused because cleanup had removed task `106`; it created no task and made no provider call. The raw artifact plus the exact-field evaluator regression preserve the evidence boundary, but the current CLI cannot regenerate an evaluator artifact from a cleaned persisted observation.

### Automatic audit decision

- **Approve the narrow real Worker functional chain `SUM(NULL) -> no_matching_records -> insufficient_evidence` and its cleanup. P0-2/P0 remain unapproved.** This does not promote the overall data path: it is one development case, the original stored evaluator artifact predates the catalog-alias evaluator repair, and broader data, hybrid, heldout, recovery, and concurrency gates are still unproved. Do not rerun tasks `105` or `106`, mutate Gold/heldout, or start P1/P5/concurrency. The next P0 action is a no-cost gate audit that selects the earliest remaining development-only data/hybrid or durable-artifact-replay contract before another paid task.

## 2026-10-13 — P0-2 durable cleaned-observation replay (passed)

- The v7 audit exposed that `run_business_evaluation` could only rebuild observations from a live task, while the mandatory cleanup removes that disposable task. A later evaluator-rule repair could therefore not produce a replacement artifact without recreating a paid task. The new `--observation-run` input accepts a schema-validated saved `EvaluationRun`, requires its unique case IDs to exactly match the selected fixture cases, rejects simulated observations, and cannot be combined with task/rejection maps or simulation. It opens no database session and invokes no Agent or model.
- Regression creates a saved normalized observation, asserts replay does not open a database, and verifies the output retains its route, model-call count, and source artifact reference. Focused evaluator/CLI, result, Router, observation, Reviewer, preparation, and trace checks passed `106`; selected Ruff and scoped diff checks passed. Worker was rebuilt and readiness remained database, Redis, object storage, and task capacity `ok`.
- The saved real task-106 artifact was replayed through the rebuilt Worker with v7 fixture and the revised catalog-alias evaluator. New artifact `backend/.evaluation-runs/p0-data-no-match-v7-r2-replay/p0-v7-replay-evaluation/run.json` has one persisted-task observation and **1/1 hard-gate pass**: data-only route, equivalent registered region scope, no-matching fingerprint, `insufficient_evidence` outcome and limitation, deterministic/numeric/citation validation, persisted partial-report boundary, budget, and security. It performed no provider call, database query, task creation, or cleanup mutation.

### Automatic audit decision

- **Approve durable replay for the v7 data-only no-match slice; P0-2/P0 remain unapproved.** This closes the evidence-retention gap for that existing trace, not hybrid data/document behavior, heldout generalization, recovery, or concurrency. Preserve tasks `105`/`106` as historical artifacts; do not modify Gold/heldout or begin P1/P5/concurrency. The next P0 action is a no-cost audit of the earliest remaining development-only hybrid insufficient-evidence contract before any new provider task.

## 2026-10-13 — P0-2 hybrid insufficient-evidence v8 (runtime safe stop proved; SQL sub-contract unresolved)

- The development-only v8 fixture uses an unknown SKU with an explicit February-to-March comparison and empty frozen document scope. An independent read-only ACME check had already established that the SKU and its controlled sales join have no matching rows. The first disposable task (`107`) exposed a separate Reviewer defect: an internal diagnostic containing unverified candidate-SQL dates was concatenated into the public insufficient-evidence answer. The numeric validator correctly rejected those numbers, but Router treated that rejection as repairable and replanned twice. It failed after eight provider calls, 15,222 tokens, 174,640 ms, and `$0.006178`; the saved evaluator artifact `backend/.evaluation-runs/p0-hybrid-v8-failed-run/evaluation/run.json` records the failure. This is a rejected Bad Case, not a passing retry.
- The minimal repair keeps the internal diagnostic in task evidence but makes the public insufficient-evidence answer a fixed, non-numeric limitation. A regression verifies a diagnostic containing `2024` and `0` is not exposed and `numbers_valid` remains true. Reviewer, Router, Worker terminal, and business-evaluation checks passed `88`; changed-file Ruff and scoped diff checks passed.
- One fresh task (`108`) under the `$0.15` server ceiling then ran through API -> Outbox -> Worker. It persisted `route=hybrid`, the correct SKU/period scope, Data and Knowledge `insufficient_evidence`, a partial report with no facts, recommendations, or citations, terminal `evidence_exhausted -> insufficient_evidence`, and deterministic schema/numeric/citation checks all passed. It stopped at the first Router decision (no replan), with four provider calls, 7,336 tokens, `$0.002896`, zero security incidents, and one local RAG call. Its 140,595 ms duration includes embedding-model cold loading after the rebuilt Worker and is not normal-latency evidence.
- The v8 evaluator is correctly **unknown**, not pass: the fixture requires a SQL result fingerprint, but Data semantic review declined to execute the otherwise safe product/month query because it cannot independently prove the requested business cause. Thus no result fingerprint exists; all other applicable gates passed. Artifact: `backend/.evaluation-runs/p0-hybrid-v8-r2-run/evaluation/run.json`. Both disposable tenants were trace-rendered and cleaned; post-cleanup tasks `107`/`108` are absent and readiness is database, Redis, object storage, and task capacity `ok`.

### Automatic audit decision

- **Reject v8 as a completed hybrid SQL slice; approve only the public-answer numeric-safety repair and the no-replan runtime behavior. P0-2/P0 remain unapproved.** Do not delete the SQL fingerprint requirement or relabel it inapplicable: the frozen case specifically requires the Data sub-problem to establish the unknown SKU/month evidence before the system refuses causal attribution. The next work is a no-cost DataAgent/semantic-review contract repair that separates a hybrid route's executable data sub-question from its document-only causal requirement, with deterministic tests before one new bounded development task. Do not modify Gold/heldout or begin P1/P5/concurrency.

## 2026-10-13 — P0-2 hybrid SQL/data-document boundary v8 r3 (passed)

- The SQL semantic-review contract now explicitly distinguishes a `hybrid` route's executable data sub-question from its document-only causal evidence; data-only queries still require complete metric, range, and scope support. Reviewer safety and hybrid SQL-review regressions, plus related Agent/Router/evaluator tests, passed `126`; Ruff and scoped diff checks passed.
- Fresh disposable task `109` executed one controlled product/month revenue comparison query, returned zero rows, persisted the canonical no-matching SHA-256 fingerprint, then completed the empty-document branch as a partial report with no confirmed fact, causal claim, recommendation, or citation. It stopped once at `no_matching_records -> insufficient_evidence`; deterministic schema/numeric/citation checks passed. Cost was `$0.002917`, with four provider calls and 7,450 tokens under the `$0.15` ceiling; cold embedding loading accounts for the 126,286 ms duration.
- `backend/.evaluation-runs/p0-hybrid-v8-r3-run/evaluation/run.json` has **1/1 hard-gate pass** for route, scope, SQL fingerprint, outcome, limitation, report persistence, deterministic checks, budget, and security. Cleanup retained the trace then removed task `109` and its disposable tenant resources; readiness remained fully `ok`.

### Automatic audit decision

- **Approve the narrow v8 hybrid no-matching data/document slice. P0-2/P0 remain unapproved.** It is one development case and does not prove heldout quality, broader hybrid data coverage, recovery, or concurrency. Do not begin P1/P5/concurrency; select the next earliest P0 development contract through a no-cost gate audit.

## 2026-10-13 — P0 cross-company HTTP rejection (passed; narrow security evidence)

- A real API request used an attacker tenant's API key against a separately created target tenant conversation. `POST /conversations/96/messages` returned `404` with the supplied correlation ID; middleware persisted `analysis_request_rejections(company_id=56, operation=conversation_message, status_code=404)`. Direct scoped reads before cleanup found zero `AnalysisTask` rows and zero joined `ModelCallRecord` rows for that request ID.
- The existing request-rejection Observation adapter evaluated the unchanged `business_gold_v1` development case `security-cross-company-request`. Artifact `backend/.evaluation-runs/p0-security-cross-company-v1-run/evaluation/run.json` has 1/1 hard-gate pass: observed rejection, no side effects, zero model calls/tokens/cost, and no security incident. Related HTTP/audit/evaluator tests passed `25 passed, 1 skipped`.
- This checks the API authorization and rejection-audit boundary only. It intentionally proves neither a business answer nor a Worker/Redis/business-database execution; the run itself must make none of those calls. The scoped cleanup removed both disposable companies/users, their resources, rejection record, and any matching task (`0/0/0/0` remaining); readiness then reported database, Redis, object storage, and task capacity `ok`.

### Automatic audit decision

- **Approve only this narrow cross-company request-rejection slice. P0-2/P0 remain unapproved.** It does not validate forged document IDs, SQL-schema injection, revocation races, a heldout security case, recovery, or concurrency. Return to the earliest unproved P0 development contract through a no-cost gate audit; do not infer phase completion from this single rejection path.

## 2026-10-13 — P0 security-evaluation boundary audit (no-cost; classification correction required)

- The remaining frozen `security_rejection` texts do not describe the same request-level mechanism as `security-cross-company-request`. An explicit empty `document_ids=[]` is a valid frozen scope for data-only and evidence-insufficient analysis paths, while a forged/non-owned document ID is the actual HTTP `422` authorization boundary. The phrase “根据未授权文档” alone is not an API document identifier and cannot safely be rejected by a lexical content filter.
- `evaluation.scenario_truth` is likewise not a request-level SQL parameter. SQL is generated inside the Worker, then `validate_sql` rejects any schema-qualified table before database connection. The direct assertion passed, and SQL validator, SQL tool, ToolRuntime document-scope, and Worker scope regressions passed `53` tests. ToolRuntime records out-of-frozen-scope/missing document inputs as `tool_document_scope_denied`; this is a runtime tool denial, not an HTTP request rejection.
- Therefore no model-free HTTP run was attempted for these three texts, and their current `security_rejection` / zero-call fixture classification is not executable evidence of the stated controls. Reclassifying a content question as an HTTP error would be a false security claim; changing frozen Gold after a run would be evaluation tuning.

### Automatic audit decision

- **Do not mark `security-empty-document-scope`, `security-sql-schema-injection`, or the heldout document-injection item passed or failed from the request-rejection adapter.** P0-2/P0 remain unapproved. The next implementation slice must add a distinct, persisted runtime-tool-denial observation contract (including no business DB execution and no out-of-scope evidence) before it can evaluate those controls; the heldout case remains untouched.

## 2026-10-14 — P0 runtime frozen-document tool denial (passed; narrow security evidence)

- Added a separate `runtime_tool_rejection` evaluation kind rather than reusing the HTTP request-rejection adapter. Its development-only fixture requires failed outcome, no route, exact persisted denial code, zero model calls/tokens, and execution prevention; unrelated business-answer checks are intentionally inapplicable. Gold and heldout fixtures were not changed.
- A fresh disposable tenant created a persisted task and execution attempt, froze one allowed document ID, then invoked `ToolRuntime` with a different document ID. The real Runtime denied it with `tool_document_scope_denied` before the local tool body could execute. The persisted observation records one denied `ToolCallRecord`, zero `ModelCallRecord` rows, `runtime_tool_denial_status=passed`, and `tool_execution_prevented_status=passed`.
- The independent evaluator CLI read that persisted record. Artifact `backend/.evaluation-runs/p0-runtime-tool-denial-v1-run/evaluation/run.json` reports 1/1 pass, hard security gate passed, zero incidents, zero model calls/tokens, and settled cost `0.000000`. Exact-ID-and-name-guarded cleanup then removed the disposable company, user, document, task, execution attempt, tool-call record, and model-call records; direct post-cleanup counts are all zero and readiness is fully `ok`.
- Focused Runtime, evaluator, observation, CLI, workflow, and terminal-result regression checks passed `130`; changed-file Ruff passed. The saved fixture and complete `EvaluationRun` artifact both parse against their Pydantic schemas. The first local artifact draft was rejected by this schema check because it omitted required fields; it was replaced with the exact complete evaluator result before this decision.

### Automatic audit decision

- **Approve only the frozen-document Runtime denial slice. P0-2/P0 remain unapproved.** This is a direct `ToolRuntime` persistence proof, not a natural API -> Outbox -> Worker prompt trace, RAG/business-database execution, model-provider behavior, SQL-schema rejection, heldout security evidence, recovery, or concurrency. The next work must still begin with a no-cost earliest-unproved-P0 gate audit; do not promote the remaining security fixtures from this result.

## 2026-10-14 — P0 normal data-only persisted baseline (passed; one development case)

- The frozen `business_gold_v1` stores semantic result labels that are not executable against the persisted SHA-256 result-fingerprint contract. Rather than change Gold after observing a run, a separate development-only fixture fixes one independently reproducible normal result: the ACME read-only query for region `EAST`, August 2025, and `sales_orders.status='delivered'` returns `1847604.72`. The expected SHA-256 is computed from the canonical persisted evidence shape `columns=["销售额"], rows=[["1847604.72"]]`; it contains no answer field in the Agent preparation payload. Heldout cases and Gold are unchanged.
- Fresh disposable task `111` ran the real API -> Outbox -> Worker chain with explicit empty document scope, a server-created source/snapshot, and task budget `$0.15`. It completed through `Planner -> semantic review -> Data (two model calls) -> Runtime SQL tool -> Reviewer -> deterministic terminal publication`. The safe metadata trace is `backend/.evaluation-runs/p0-data-revenue-v1-run/traces/task-111.html`; it excludes question text, prompts, SQL, tool arguments/results, report body, and event details.
- Independent persisted-observation evaluation is saved in `backend/.evaluation-runs/p0-data-revenue-v1-run/evaluation/run.json`: 1/1 hard-gate pass, correct `data_only` route/entity/period, matching result fingerprint, numeric/deterministic/citation checks, persisted report, and zero security incidents. It used `deepseek:deepseek-v4-flash`, five model calls (Planner 1, semantic review 1, Data 2, Reviewer 1), 8,561 tokens, 6,993 ms, and settled `$0.003203`; the model budget snapshot was `$0.15` with no unknown-cost calls.
- The saved fixture/artifact parse against `EvaluationFixture`/`EvaluationRun`; focused metric, SQL, evaluator, observation, Runtime, workflow, and terminal-result regression checks passed `142`, and changed-file Ruff passed. Manifest-limited cleanup rendered the trace then removed task `111`, company `60`, user `68`, data source `49`, snapshot `47`, model and tool records (all direct post-cleanup counts `0`); readiness remains database, Redis, object storage, and task capacity `ok`.

### Automatic audit decision

- **Approve this one normal data-only development baseline. P0-2/P0 remain unapproved.** It gives a current successful Worker/model/controlled-SQL/terminal-publication reference and a measured `t=6,993 ms`, `c=$0.003203` for this narrow workload. It is neither a candidate comparison nor proof for other metrics, hybrid/RAG answers, frozen heldout cases, multi-case quality, recovery, or capacity; do not promote a default or start P1/P5/concurrency from this one result. The next P0 action is a no-cost selection audit for the next independently specified development contract, preferably a normal source-supported knowledge or hybrid case not represented by this data-only baseline.

## 2026-10-14 — P0-0 candidate fingerprint and non-E2E test baseline (partial; P0 remains unapproved)

- The reusable `scripts/ops/collect-baseline-audit.ps1` initially could not fingerprint this Windows workspace: pip printed the non-ASCII project path under `cp950`, and Git returned quoted escaped names for untracked Chinese PDF paths. The minimal measurement-only repair sets `PYTHONUTF8=1`, uses `core.quotePath=false` for untracked filenames, writes P0 artifacts to ignored `artifacts/p0/<run_id>/`, and records pytest skip reasons. It also uses pytest `--import-mode=importlib`; the previous default importer confused `documents/test_storage.py` with `input_artifacts/test_storage.py`, while the configured mode collects both files separately.
- Candidate artifact: `artifacts/p0/candidate-p0-0-20261014-r3/`. It records HEAD `a0d8578a94fc0d0c7759b018c23a5d530f83a391`, Python `3.13.14`, pytest `9.1.1`, Ruff `0.16.1`, Alembic head `v9a0b1c2d3e4`, 251 untracked input paths, and tracked-diff SHA-256 `ce857d00d82a47b8c5259ca79535db004474918b408c9e43a627e5f0bfa79cac`. No generated `artifacts/p0` path entered that source manifest. `pytest --collect-only -q` collected 780 tests (exit 0); `ruff check app tests` exited 1 with 330 findings; `pytest tests -q -rs -m "not e2e and not slow"` exited 1 with 766 passed, 3 failed, 4 skipped, and 7 deselected in 35.92 seconds. `git diff --check` exited 0; its CRLF warnings were not treated as a clean-tree claim.
- Candidate failures are classified, not repaired: (1) `test_bootstrap_owner_only_works_before_any_company` deletes `companies` before the independently committed `documents` fixture data, so the database FK prevents the test setup; this is test-isolation/cleanup coupling, not a proven bootstrap behavior failure. (2) `test_admin_can_list_only_current_company_pending_review_requests` expects report schema `1.1`, while `FinalAnalysisReport` now defaults to `1.2`; this is a pending API-contract decision, not permission to weaken the assertion. (3) `test_initiate_attachment_upload_session_never_falls_back_to_local_disk` expects unavailable direct storage (503) but received a created upload session (201); this is a pending test-environment/storage-contract mismatch. The four skips are explicit: two LocalStack E2E proofs require `RUN_LOCAL_OBJECT_STORAGE_E2E=1`, and two SQL-executor tests require the Docker business database. They are not counted as passes.
- A detached `a0d8578a` worktree was created under `tmp/evaluation-baseline-baseline-p0-0-a0d8578a-r1/` and retained. Its first collection failed before tests because the clean worktree has no `.env` and that revision requires a nonempty `DATABASE_PASSWORD`. A second run received the existing `.env` only as a process test-environment file; it still failed because that file contains object-storage variables but no database password. No secret values were written to artifacts. Thus the clean-HEAD test baseline, container/source equivalence, real Worker smoke, and repeat-fingerprint proof remain unknown. Docker Compose config exited 0, but `docker compose images` exited 1 because Docker referenced a missing image ID; no E2E claim is permitted.

### Automatic audit decision

- **Adopt only the P0-0 measurement harness repairs and the candidate-run record. P0-0 and P0 remain unapproved.** Do not repair the three candidate test failures, modify Gold/holdout, or start model evaluation from this result. The next decision is whether to provide a controlled, non-secret test-environment contract that lets clean `a0d8578a` collect and run; then rerun both baseline and unchanged candidate fingerprints before choosing any failure-specific repair.

## 2026-10-14 — P0-0 clean-source baseline environment contract (partial; P0 remains unapproved)

- Added tracked `backend/.env.p0.example` and an explicit `.gitignore` exception. It contains only the P0 local test endpoints, database names/users, and two replacement password placeholders; `.env.p0.local` remains ignored. The collector records only the local environment file SHA-256 and variable names, never values. The first clean run reused the already ignored `backend/.env`; it did not copy a credential file into the detached worktree or artifacts.
- Artifact `artifacts/p0/baseline-p0-0-a0d8578a-r4/` is a detached worktree at exactly `a0d8578a94fc0d0c7759b018c23a5d530f83a391`. Its source manifest has `tracked_diff_sha256=null`, zero untracked files, and five dependency hashes. This required a collector correction: forcing `core.autocrlf=false` falsely treated the Windows CRLF checkout as changed source. The corrected collection uses normal Git filtering; the r4 worktree has empty `git status`.
- The controlled environment lets pytest collect: `464` tests, exit `0`. Static checking exits `1` with `386` Ruff findings. Non-E2E tests exit `1`: `294 passed, 2 skipped, 5 deselected, 163 errors` in `27.13s`. The first and repeated setup error is `Can't locate revision identified by 'v9a0b1c2d3e4'`: the shared local `agent_platform_test` database is stamped with a migration that the frozen baseline source does not contain. The two skips require the Docker business database. This is a source-version/test-database incompatibility, not a passing baseline and not permission to edit assertions.
- Docker configuration inside the clean worktree remains unproved: Compose exits `1` because its declared ignored `backend/.env` does not exist there. The collector process can load the secure file for Python without materializing it in the worktree, but that does not satisfy Compose's file requirement. No container, migration, database reset, model call, Gold/holdout change, or E2E claim was made.

### Automatic audit decision

- **Adopt the non-secret local test-environment contract and corrected source fingerprinting; reject P0-0/P0 completion.** The next safe technical slice is a separately named baseline database initialized only with the frozen `a0d8578a` migrations, then the unchanged r4 command is rerun against it. Do not drop, downgrade, or reuse the shared `agent_platform_test` database; its current contents are newer than the baseline and it is not a valid historical baseline fixture.

## 2026-10-14 — P0-0 isolated clean-source test baseline (partial; P0 remains unapproved)

- The test fixture hard-codes `agent_platform_test`; merely creating a differently named database would not isolate the baseline. A new container named `agent-p0-baseline-postgres-a0d8578a` was therefore started on `127.0.0.1:5437`, with no host data volume and no operation against the shared test database. PostgreSQL itself reported `accepting connections`; the bootstrap created its own `agent_platform_test` for `agent_migrator`. No existing database was reset, downgraded, or deleted.
- Artifact `artifacts/p0/baseline-p0-0-a0d8578a-r6-isolated-min-env/` uses clean detached source `a0d8578a94fc0d0c7759b018c23a5d530f83a391`, null tracked-diff hash, zero untracked files, baseline Alembic head/database version `c9e4a1f7b2d8`, and the explicitly recorded non-secret port override `DATABASE_PORT=5437`. The runner now imports only the ten database variables named by the P0 template; model/API and object-storage settings in the developer `.env` are not passed into this test run.
- `pytest --collect-only -q` collected `464` (exit `0`). `pytest tests -q -rs -m "not e2e and not slow"` passed: `457 passed, 2 skipped, 5 deselected in 21.18s` (exit `0`). The two skips still require the Docker business database and are not evidence of that dependency. `ruff check app tests` remains exit `1` with `386` findings, so this is a test baseline only, not a green quality gate. The clean worktree's Compose inspection remains unavailable because Compose requires its own ignored `backend/.env`, which was intentionally not copied there.
- The prior r5 isolated run had one failure because it imported the full developer `.env`, enabling object storage and returning `201` where the frozen baseline test correctly expects no configured direct-upload backend (`503`). r6 removes that unrelated credential/configuration leakage rather than weakening the test.

### Automatic audit decision

- **Approve the narrow clean-source, isolated non-E2E pytest baseline; reject P0-0/P0 completion.** The candidate has not yet been executed under the same isolated/minimal configuration, static checks are red, Docker business/object-storage/Worker E2E dependencies are unproved, and the frozen test count differs from the dirty candidate. Preserve the isolated container for a comparable candidate run; do not treat r6 as a release or production claim.

## 2026-10-14 — P0-0 executable candidate snapshot (frozen without commit; partial)

- By explicit approval, the candidate was frozen without `git commit`, `merge`, `push`, deletion, or movement of user files. Snapshot `artifacts/p0/candidate-p0-0-snapshot-20261014-r3/candidate-snapshot/` is based on `a0d8578a94fc0d0c7759b018c23a5d530f83a391` and contains a binary `candidate.patch`, an `untracked-files.zip`, per-scope path lists, excluded-path list, and SHA-256 manifest. The candidate collector now diffs against `HEAD`, so staged and unstaged tracked changes are both included rather than only the unstaged subset.
- Scope is intentionally only the approved P0 executable surface: `backend/` except historical `backend/.evaluation-runs/`, `scripts/ops/`, `docs/`, and root `AGENTS.md`, `.gitignore`, `docker-compose.yml`, and `README.md`. The snapshot contains `135` changed tracked paths and `89` selected untracked paths. `166` paths were explicitly excluded, including `output/` resumé/PDF material and historical evaluation-run artifacts; ignored `.env`, virtual environments, and prior `artifacts/p0` output are not included.
- Reproducibility checks passed: the recorded patch and ZIP hashes equal freshly recomputed SHA-256 values; all `89` ZIP entries equal `untracked-paths.txt`; and `git apply --check` accepts the patch against the clean `a0d8578a` r6 worktree. Candidate collection records `780` tests (exit `0`). No full candidate test suite, database migration, Docker Compose service, Worker, model, or business-database call was run for this snapshot.
- Earlier candidate snapshot attempts remain preserved but are not evidence: r1 could not create a ZIP because Windows `tar.exe` could not write to the Unicode artifact path; r2 omitted changed root `AGENTS.md` from its allowed scope. r3 replaces neither artifact and is the only snapshot referenced by this decision.

### Automatic audit decision

- **Adopt r3 as the immutable P0 executable candidate source snapshot; P0-0/P0 remain unapproved.** The next permitted P0-0 action is to materialize r3 in a separate temporary worktree, point it at the already isolated test PostgreSQL instance, and run the unchanged non-E2E candidate checks under the same minimal environment. Static failures, skipped external dependencies, and all business/Worker/model E2E claims remain unproved.

## 2026-10-14 — P0-0 candidate snapshot r4 correction (adopted)

- The r3 snapshot correctly preserved executable files but included the append-only `docs/evidence.md`. Recording r3 then necessarily changed that ledger, making the snapshot self-referential rather than a stable executable-source boundary. No prior evidence entry was edited. The snapshot scope now explicitly excludes `docs/evidence.md`; the ledger remains the audit index for snapshots rather than snapshot input.
- The adopted snapshot is `artifacts/p0/candidate-p0-0-snapshot-20261014-r4/candidate-snapshot/`, still based on `a0d8578a94fc0d0c7759b018c23a5d530f83a391`. It contains `135` changed tracked paths and `88` selected untracked paths. It explicitly excludes `167` paths, including `docs/evidence.md`, `output/` personal resumé/PDF material, and historical `backend/.evaluation-runs/` artifacts. Ignored secrets, virtual environments, and prior P0 artifacts remain excluded.
- Verification passed: binary patch SHA-256 and ZIP SHA-256 equal the manifest; all `88` ZIP entries equal the untracked-path manifest; `git apply --check` accepts the patch against the clean frozen r6 worktree; candidate collection exits `0`. r3 and earlier attempts are retained as superseded diagnostic artifacts only. No full tests, migration, Compose service, Worker, model, or business-database action ran.

### Automatic audit decision

- **Supersede the prior r3 source-snapshot decision and adopt r4 as the immutable executable candidate snapshot. P0-0/P0 remain unapproved.** The next P0-0 operation may materialize r4 in an isolated temporary worktree and run the same non-E2E test command against the preserved isolated PostgreSQL instance; no existing source, personal output, shared database, Gold, holdout, or evidence history may be changed.

## 2026-10-14 — P0-0 isolated candidate baseline and reproducible fingerprint (partial; P0 remains unapproved)

- Snapshot r4 was materialized into a separate detached worktree from `a0d8578a`; its patch passed `git apply --check`, and all `88` selected untracked files were restored. The run used the same minimal ten-key test environment and isolated PostgreSQL port `5437` as the clean-source r6 baseline. It did not copy an `.env` into the worktree, access the shared test database, run a migration outside the session fixture, invoke a model, or access the business database.
- Candidate non-E2E result is recorded at `tmp/evaluation-candidate-p0-0-r4-isolated/artifacts/p0/candidate-p0-0-r4-isolated-min-env/`: collection `780` (exit `0`); tests exit `1`: `767 passed, 2 failed, 4 skipped, 7 deselected in 36.98s`; Ruff exit `1`: `330` findings (`158` autofixable, `25` additional unsafe fixes). The four skips are classified: two require the Compose LocalStack proof, and two require the Docker business database. Compose inspection in the source worktree is unknown because its intentionally absent ignored `backend/.env` is required by the Compose file.
- The two candidate test failures are classified and not repaired: (1) `test_admin_can_list_only_current_company_pending_review_requests` expects report schema `1.1`, while the candidate returns `1.2`; this is an unresolved report API contract, not authority to weaken an assertion. (2) `test_stdio_server_exposes_only_evidence_read` starts its MCP subprocess without passing the minimal test database environment; without a worktree `.env`, the child correctly fails Settings validation for an empty database password. This is a test/subprocess environment-contract failure. MCP is already present in the candidate snapshot but is outside the P0 construction scope, so no MCP feature or behavior was added or repaired.
- r4's raw `git diff --binary` hash differed after materialization despite matching source paths; per-file Git filtered hashes showed no content mismatch. The measurement harness was corrected to fingerprint sorted `{path,status,filtered blob hash}` entries instead of hashing CRLF-sensitive diff text. It also expanded the P0-document allowlist to include changed `CONTRIBUTING.md`, `PRODUCT.md`, and `SECURITY.md`. r5 remains a superseded diagnostic snapshot because those documents were initially excluded. Adopted r6 snapshot and independently materialized r6 worktree have the identical canonical tracked-change SHA-256 `7ae667d6a7c6cddb0da31ecb25ed7d61cac16a904a8cb98f560a166253c0ff0d`, `138` tracked changes, `88` selected untracked files, matching patch/ZIP hashes, and collection exit `0`.

### Automatic audit decision

- **Adopt r6 as the reproducible executable candidate fingerprint and adopt the r4 isolated candidate test record as a classified failing baseline. P0-0/P0 remain unapproved.** Do not change the two failing assertions, introduce or expand MCP, bulk-fix Ruff, or claim container/Worker/model/business-database proof. The next P0 decision is whether to treat the report-schema assertion and stdio subprocess configuration as two explicitly scoped measurement/contract repairs, each with a red/green test, or to retain them as known candidate failures while proceeding only with the next no-cost P0 gate audit.

## 2026-10-14 — P0-0 candidate stdio subprocess-environment repair (partial; P0 remains unapproved)

- Root cause was reproduced in the isolated r4 candidate: `test_stdio_server_exposes_only_evidence_read` constructed `StdioServerParameters` directly, so the child process did not receive the deliberately minimal test database environment. The already-existing production factory `McpEvidenceReadTool.stdio()` supplies exactly that constrained environment. The test now uses the factory and asserts its returned server parameters; no MCP server behavior, tool catalogue, protocol, authorization rule, or environment allowlist was changed.
- Snapshot `artifacts/p0/candidate-p0-0-snapshot-20261014-r8/candidate-snapshot/` was frozen without commit. It is based on `a0d8578a94fc0d0c7759b018c23a5d530f83a391`, retains the same canonical tracked fingerprint `7ae667d6a7c6cddb0da31ecb25ed7d61cac16a904a8cb98f560a166253c0ff0d` over `138` tracked changes, and selects `88` approved untracked files. Patch SHA-256 is `32a32202cc14fc88cc0ac745ab211b84cce1d5701fe4def00027854b626d6ba9`; ZIP SHA-256 is `6e590eb5940674c8136182fbd0a74ccc6cd377e188442c77e177a4c1f21cc05b`. The patch passed `git apply --check` and application into fresh detached worktree `tmp/evaluation-candidate-p0-0-r8-isolated/`.
- Under the same ten-key minimal environment, isolated PostgreSQL `127.0.0.1:5437`, and `PYTHONUTF8=1` used by the collector, `pytest tests -q -rs -m "not e2e and not slow"` now reports `768 passed, 1 failed, 4 skipped, 7 deselected in 33.43s`. The stdio test is no longer a failure. The only failing test is the separately classified review-report schema assertion (`1.1` expected, `1.2` returned). The skips remain two LocalStack E2E and two Docker business-database dependencies. `ruff check app tests` still exits `1` with `330` findings (`158` autofixable, `25` further unsafe); no bulk lint change was made.
- The initial r8 collector invocation was interrupted after writing the Ruff artifact by the desktop terminal's ~30-second command-session limit, before it wrote its final `checks.json`. The preserved matching direct pytest rerun is `tmp/evaluation-candidate-p0-0-r8-isolated/artifacts/p0/candidate-p0-0-r8-isolated-min-env/pytest-rerun-pythonutf8.txt`; it uses the same interpreter, source worktree, database environment, port override, and pytest expression. A first manual rerun without `PYTHONUTF8=1` additionally exposed Windows `cp950` decoding errors in subprocess-output tests; it is diagnostic only and is not the recorded result.

### Automatic audit decision

- **Adopt only the narrow stdio test-environment repair and r8 isolated candidate result. P0-0/P0 remain unapproved.** The unresolved review schema contract, red Ruff gate, skipped external dependencies, Compose environment boundary, and all Worker/model/business-database E2E claims remain open. Do not alter the remaining schema assertion without an explicit contract decision; do not add MCP capability or start a later phase from this test-only improvement.

## 2026-10-15 — P0-0 Review API schema-version contract decision (partial; P0 remains unapproved)

- User selected `1.2` as the current formal `report_draft.schema_version` returned by the Review API. Root-cause inspection showed the review fixture omits `schema_version`, while `FinalAnalysisReport` defaults it to `1.2`; the prior `1.1` assertion was therefore stale. The sole source change updates that integration assertion to `1.2`. No report field, validator, migration, API path, compatibility layer, or runtime behavior changed.
- Frozen r9 source snapshot is `artifacts/p0/candidate-p0-0-snapshot-20261014-r9/candidate-snapshot/`, based on `a0d8578a94fc0d0c7759b018c23a5d530f83a391`. Its patch SHA-256 is `ce94e67413cdc396231ed016c44b431ba5e27d2d0676f3af03ced8035b4c5d3c`; the unchanged selected-untracked ZIP SHA-256 is `6e590eb5940674c8136182fbd0a74ccc6cd377e188442c77e177a4c1f21cc05b`. `git apply --check` accepted the patch and it was applied to fresh detached worktree `tmp/evaluation-candidate-p0-0-r9-isolated/`.
- In the same minimal ten-key environment, isolated PostgreSQL on port `5437`, and `PYTHONUTF8=1`, full non-E2E pytest is now green: `769 passed, 4 skipped, 7 deselected in 37.08s` (exit `0`). The four skips remain two LocalStack E2E and two Docker business-database dependencies; they are not passes or external-dependency proof. Artifact: `tmp/evaluation-candidate-p0-0-r9-isolated/artifacts/p0/candidate-p0-0-r9-isolated-min-env/pytest.txt`.
- `ruff check app tests` remains exit `1` with `330` findings (`158` auto-fixable, `25` additional unsafe). The candidate's broader P0 external dependency, Compose, Worker, model, business-database, and heldout evidence remain unrun/unproved.

### Automatic audit decision

- **Adopt the explicit `1.2` Review API contract decision and the r9 non-E2E pytest result; P0-0/P0 remain unapproved.** Do not infer a complete schema-compatibility policy solely from this default value: current source allows both `1.1` and `1.2` attachment citations and does not yet version-gate all newer report fields. Do not start later phases or change schema behavior without a separately scoped compatibility contract.

## 2026-10-15 — P0 next development-contract selection audit (no provider call)

- After the r9 candidate's comparable non-E2E suite became green, the earliest independently specified normal case not represented by the current data-only baseline is `hybrid-east-delivered-revenue-causality-boundary` in `business-hybrid-revenue-causality-development-v1`. It requires one known deterministic SQL amount for East-region August 2025 delivered orders, one frozen authorized document, a source-supported CUST-0001 contract-expiry/pause relation, and an explicit non-unique-cause qualification. This is a development-only fixture; no Gold or heldout input was changed.
- The two retained prior artifacts are classified rather than erased: task `112` incorrectly normalized the mixed request to `knowledge_only` and never queried data; task `113` used both SQL and RAG and passed route, scope, SQL fingerprint, numeric, citation, claim, qualification, persistence, deterministic-validation, and security gates, but failed because a negated “唯一原因” qualification was treated as forbidden and the hybrid report was downgraded to partial. Current deterministic regressions cover the negated-forbidden-claim boundary and mixed data-plus-document route.
- Static preflight in the r9 isolated worktree, using the same minimal ten-key database environment, isolated PostgreSQL port `5437`, and `PYTHONUTF8=1`, passed `94` Planner/Evaluator/Composer/Reviewer tests in `1.21s`. Docker server probe returned `29.6.1`. A first preflight omitted the required process-only database values and failed Settings validation before collection; it is a command-environment diagnostic, not a source failure. The selected-file Ruff check remains red with `20` existing findings, primarily `FLY002`/`ISC004` in the long planner prompt and its tests; no broad lint rewrite was made or claimed.

### Automatic audit decision

- **Adopt only the next-case selection and static preflight; P0-2/P0 remain unapproved.** No disposable tenant/task, provider call, model cost, document upload, Worker execution, or cleanup occurred. A real run needs explicit authorization for one disposable development task, model-cost ceiling `$0.15`, artifact-before-cleanup, and automatic hard-gate audit. Its result must not be promoted if any applicable gate fails.

## 2026-10-15 — P0 real hybrid development run and approved-review Outbox repair (partial)

- Under explicit authorization, exactly one disposable development task (`115`) was submitted for `hybrid-east-delivered-revenue-causality-boundary`, with a `$0.15` ceiling. Its persisted model ledger reports `6` calls, `11,212` tokens, and settled cost `$0.004486`; the task consumed no additional model calls when its already-created draft was later approved and published.
- The first attempt to approve its pending causal-hypothesis review exposed a real workflow defect: the original delivery event (`107`) was already `worker_claimed`, but `review.service.approve_review_request` creates a second event for the same task. The database's `uq_analysis_task_outbox_events_task_id` blocked that event, and the approval transaction rolled back. The P0 repair removes only that per-task uniqueness, adds migration `w0a1b2c3d4e5` to replace it with ordinary `task_id` index `ix_analysis_task_outbox_events_task_id`, and extends the existing review test to cover a prior `worker_claimed` event followed by approval.
- The focused red test failed on the old unique constraint. After the repair, `pytest tests/modules/reviews/test_review_service.py tests/modules/workflow/test_outbox_service.py -q` passed `7`; focused Ruff and format checks passed; the platform database reports Alembic head `w0a1b2c3d4e5`, no old unique constraint, and the replacement ordinary index. The normal application account could not alter a migrator-owned table, so the exact migration DDL and version update ran in one PostgreSQL transaction under `SET LOCAL ROLE agent_migrator`; it did not grant the application account extra privilege.
- The retried authorized approval created event `109`, was broker-accepted, and the Worker completed task `115` with `publication.decision=published`. Terminal evaluation was saved before cleanup at `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r3-run/evaluation-terminal/`; the generated trace is `traces/task-115.html`. Manifest cleanup then completed for its listed disposable company, user, membership, data source, and schema snapshot.
- This real development evaluation is not a passing gate: it passed route, entity scope, SQL fingerprint, numeric consistency, citation scope, facts, claims, qualification, budget, persistence, deterministic validation, and security, but hard-gate failed solely at `forbidden_claim_free`. The response explicitly says the documents cannot prove a “唯一原因”, but the evaluator treated that negated qualification as a forbidden substring match. The earlier pre-approval evaluation artifact is retained as historical context; terminal artifact is authoritative for task status.
- `alembic check` remains red for pre-existing broad metadata drift outside this slice, including historical tables and unrelated indexes. It is not treated as a successful migration-schema proof and was not repaired.
- Frozen candidate snapshot `artifacts/p0/candidate-p0-0-snapshot-20261015-r10/candidate-snapshot/` is based on `a0d8578a94fc0d0c7759b018c23a5d530f83a391`, contains `138` changed tracked paths and `89` approved untracked paths, and excludes `330` non-P0 paths including evaluation runs, personal output, and this ledger. Patch SHA-256 is `77a234f4a7347510c1985508f11a34a0fd77638a89cbd02f4b0c75083061442c`; ZIP SHA-256 is `04e99b09b603d50ac0f08d20a1297b136d014d1b47345a184647fe00d0e44394`. Both equal the manifest, and `git apply --check` passed against the clean frozen r6 worktree. No new full-suite or provider run was made for the snapshot.

### Automatic audit decision

- **Adopt the narrow Outbox approval-republish repair, its focused regression, the real single-task execution evidence, and manifest cleanup. Reject P0/P0-2 completion.** The evaluator’s negated-forbidden-claim logic must be separately repaired and re-evaluated; external dependency/heldout evidence and the global Alembic metadata drift remain unproved.

## 2026-10-15 — P0 negated-forbidden-claim evaluator repair (partial; P0 remains unapproved)

- The terminal artifact for task `115` was replayed from its saved normalized `persisted_task` observation. It revealed three separate false-positive forms for the forbidden text `唯一原因`: `不能仅凭…断言为…唯一原因`, `不足以证明…唯一原因`, and `能否证明…唯一原因，…不足以判断/无法给出结论`. These are negated or unanswered causal assertions, not positive single-cause claims. The original evaluator had a fixed 24-character lookback and did not recognize all three forms.
- `backend/app/modules/evaluation/business.py` now scopes qualified negation to the preceding sentence or semicolon clause, recognizes the two observed preceding markers, and recognizes the observed `能否证明` question only when that same sentence has the explicit negative-resolution suffix. `tests/modules/evaluation/test_business_evaluation.py` preserves the full normalized observed wording across both `actual_confirmed_facts` and `actual_supported_claims`. The focused regression was red before each newly observed form was covered, then green after the repair.
- Verification: `pytest tests/modules/evaluation/test_business_evaluation.py -q` passed `50`; selected-file `ruff check` passed; the modified test is Ruff-formatted; and `git diff --check` passed. `ruff format --check app/modules/evaluation/business.py` remains red only for an already-present, out-of-slice formatting rewrite at line `314`; no unrelated formatting was applied.
- Replay artifact `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r3-run/evaluation-terminal-replay-source-r3/` now reports `forbidden_claim_free=true`, case `passed=true`, and `hard_gate_passed=true`, while retaining the original `6` model calls, `11,212` tokens, and `$0.004486` as observed data. This replay made no new model, Worker, database, or cleanup operation; it proves the revised deterministic evaluator against a saved real observation, not a new end-to-end run.
- Frozen snapshot `artifacts/p0/candidate-p0-0-snapshot-20261015-r11-final/candidate-snapshot/` is based on `a0d8578a94fc0d0c7759b018c23a5d530f83a391`, has `138` tracked and `89` selected untracked paths, and excludes `336` paths including this ledger and all historical evaluation runs. Patch SHA-256 `c657b9566cd2e5bb16f9e78609f710ba22d241412ef4e2168ea458d2a094c987` and ZIP SHA-256 `04e99b09b603d50ac0f08d20a1297b136d014d1b47345a184647fe00d0e44394` match its manifest; ZIP entries equal the untracked manifest, and `git apply --check` passed against the clean r6 baseline worktree. Two earlier r11 attempts are retained as incomplete diagnostics: Windows PowerShell lacks the collector's `SHA256.HashData`, and the first shell treated an existing CRLF warning as fatal.

### Automatic audit decision

- **Adopt only the evaluator repair, regression, saved-observation replay, and r11 executable snapshot. Reject P0/P0-2 completion.** The passed replay does not replace a current-source/container real run, heldout evidence, external dependency proof, or resolution of the global Alembic metadata drift.

## 2026-10-15 — P0 evaluator runtime-image replay (partial; P0 remains unapproved)

- The post-r11 workspace hash of `backend/app/modules/evaluation/business.py` was `381230019a7652d949081094c73dfe2fcd9a5db51918b832ec45200f4984c7f4`, while the long-running API and Worker containers still had the pre-repair hash `a660137b71ff65d32786ab9ebb3e310384f2e0b6d82cfd55998cddf90cdc735f`. They do not bind-mount `/app`, so host replay alone could not prove the runtime evaluator version.
- Built only the isolated Compose `evaluation` image from the current candidate source. It contains the workspace hash above. An ephemeral `evaluation` container mounted the saved task-115 evaluation input read-only and wrote its replay output to `artifacts/p0/p0-0-evaluator-runtime-replay-20261015-r1/`; it was removed automatically. API, Worker, report-worker, databases, Redis, and the business database were not restarted or written by this replay.
- Artifact `run.json` SHA-256 is `efa1812b5e7334e940d4aa1b78953f19b2b24c25617ce4daf3c9ba5222889820`; `report.md` SHA-256 is `6c33eb874e787fa87ee7f61ed1686b8b40bc54f85211aed9ef646466cfbdbca5`. It uses `persisted_task=1`, retains the prior observation's `6` calls, `11,212` tokens, and `$0.004486`, and reports `forbidden_claim_free=true`, case pass, and hard gate pass. No Provider request, fresh Worker execution, database fixture, model cost, or cleanup operation occurred.

### Automatic audit decision

- **Adopt the current-source evaluator-image replay only. Reject P0/P0-2 completion.** It closes evaluator source-to-isolated-container parity for this saved observation, but does not align/restart the long-running API/Worker, rerun the full main chain under the repaired source, provide heldout or external-dependency evidence, or resolve global Alembic metadata drift.

## 2026-10-15 — P0 idle-window main-chain image alignment (partial; P0 remains unapproved)

- Before rollout, Redis queues `celery` and `reports` were both zero; both Workers reported no active, reserved, or scheduled task; durable analysis-task inflight count was zero. The only `worker_claimed` Outbox event was event `106` for task `114`, whose task status is `awaiting_review`, not a running execution. This was inspected before any container restart.
- Built and force-recreated only `api`, `worker`, and `report-worker` with `--no-deps`; PostgreSQL, Redis, the business database, migration service, volumes, beat, and other services were not restarted or removed. The source SHA-256 for `app/modules/evaluation/business.py` and all three recreated containers is `381230019a7652d949081094c73dfe2fcd9a5db51918b832ec45200f4984c7f4`.
- After rollout, `/health/live` and `/health/ready` both returned `200`; both Workers rejoined their expected queues; broker depths and active/reserved/scheduled task lists remained empty; event `106` remained `worker_claimed` and task `114` remained `awaiting_review`. No model request, task submission, database fixture creation, migration, provider charge, queue deletion, or volume deletion occurred.

### Automatic audit decision

- **Adopt main-chain candidate-image alignment only. Reject P0/P0-2 completion.** A fresh real development run under the repaired image would require a new explicitly authorized disposable task and new model-cost ceiling because the prior task `115` and its fixture were cleaned; replay is not a substitute.
## 2026-10-15 — P0 real hybrid development rerun r4: terminal failure captured and cleaned (partial; P0 remains unapproved)

- Under the explicit one-task authorization, exactly one disposable development task (`116`) ran the unchanged frozen `hybrid-east-delivered-revenue-causality-boundary` case. Its fixture remains `business-hybrid-revenue-causality-development-v1` (`c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c`), against one frozen document (`b81016c831b861937c78890e3603c8850cd64f33d4a500a09297606827318041`); no Gold, heldout case, threshold, or corpus input changed.
- The task reached `knowledge_node`, completed its SQL and RAG tools, then failed without retry immediately after entering `reviewer_node`: `TypeError: Object of type date is not JSON serializable`. The persisted task ledger recorded `5` provider model calls, `8,892` tokens, and settled cost `$0.003790`, below the authorized `$0.15` ceiling. This is a workflow/runtime failure, not a quality pass and not a security incident.
- Persisted-observation evaluation was saved before cleanup at `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r4-run/evaluation-terminal/run.json` (SHA-256 `0fab211bfa170211691b8b78491d6788629165f8a95a4fb5e1f0fb20d6c6c901`) and `report.md` (SHA-256 `96faf8bf46ffdabadde064fb19c5412c6bd2a9fd021ad21821fd4deaf7b7e9733f`). It reports 1/1 failed, trusted success rate `0.00%`, and hard gate `failed`; `unknown` security/deterministic evidence was not converted to pass. The source trace is `traces/task-116.html` (SHA-256 `1427e93df10b3f7adcfaea1cfe950706919a5a19c53fe52ddd402b15233b4c35`), with durable event, model-call, terminal-row, and Worker-error excerpts adjacent to it.
- Authorized cleanup ran only after terminal capture and trace creation. The manifest now records `cleanup.state=completed`; direct post-cleanup queries found no task `116`, disposable company `65`, user `73`, data source `54`, schema snapshot `52`, or document `34`. No retry or additional provider call occurred during evaluation or cleanup.

### Automatic audit decision

- **Reject this rerun as a candidate success; preserve it as a reproducible P0 Bad Case. P0 remains unapproved.** The next scoped action, if approved, is root-cause isolation and a red/green regression for the reviewer-node date serialization failure; it must not rerun a real provider task without a separate authorization.

## 2026-10-15 — P0 reviewer-node date serialization repair (partial; P0 remains unapproved)

- Root-cause tracing found the shared SQL evidence normalizer `DataAgent._make_json_safe` converted `Decimal` but left Python `date` values unchanged. A real task's raw intermediate state was removed by the authorized cleanup, so its precise SQL row is not recoverable; however, the defect is independently reproduced by a controlled SQL-tool result containing `date(2025, 8, 31)`. That old behavior leaves the `date` in Agent evidence and matches the terminal `Object of type date is not JSON serializable` class seen after `reviewer_node`.
- The regression changed the existing JSON-serialization test to include both a date and decimal result row. It failed before the repair, observing `datetime.date(2025, 8, 31)` where JSON text was required. The minimal fix imports `date` and returns `date.isoformat()` in `_make_json_safe`; `datetime` is also covered because it subclasses `date`.
- Fresh isolated evaluation-container verification after the fix: `pytest tests/modules/analysis/test_agents.py tests/modules/workflow/test_workflow.py tests/modules/reporting/test_reviewer_validators.py -q` passed `92`; `ruff check --ignore EXE002 app/modules/analysis/data_agent.py tests/modules/analysis/test_agents.py` passed; and `git diff --check` for the two touched files passed. Unignored Ruff still reports the pre-existing executable-bit/shebang rule on both already-executable Python files, and `ruff format --check` proposes broad pre-existing CRLF/format rewrites; neither was altered.

### Automatic audit decision

- **Adopt the narrow source-level serialization repair and its red/green regression; reject a real-main-chain success claim. P0 remains unapproved.** The original task's exact date column cannot be reconstructed after authorized cleanup, and no new provider task, Worker execution, cost, or container rollout was run. A new real rerun remains separately authorized work, not an implied consequence of this unit-level repair.

## 2026-10-15 — P0 real hybrid development rerun r5: date repair reaches review boundary; conversation-status contract failure captured and cleaned (partial; P0 remains unapproved)

- Under the already-authorized one-task `$0.15` ceiling, exactly one disposable development task (`117`) ran the unchanged frozen `hybrid-east-delivered-revenue-causality-boundary` fixture (`c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c`) and one frozen document (`b81016c831b861937c78890e3603c8850cd64f33d4a500a09297606827318041`). The recreated API, Worker, and report-Worker all contained the repaired `data_agent.py` SHA-256 `50c7e06e1ad0f0e6047ecf962ab2ac96494ebe00abf5a939be2a646ba626258f`; no Gold or heldout input was changed.
- The prior date-serialization failure did not recur. Persisted workflow events show Planner, SQL, Knowledge, Reviewer, and Smart Router completed; deterministic validation passed; the task result was saved with `publication.decision=awaiting_human_review` and a pending causal-hypothesis review request. The model ledger has six billed provider calls, `10,904` tokens, and settled cost `$0.0042882`, plus two successful zero-cost local retrieval records.
- A distinct post-result defect then occurred while synchronizing the assistant conversation message: `conversation_messages.status='awaiting_review'` violated `ck_conversation_messages_status_values`, whose allowed contract does not include that state. The task remained `awaiting_review`, so the persisted-task evaluator correctly refused it as not terminal (captured exit `1`) rather than manufacturing a pass. No human review decision or report publication was performed.
- Terminal task row, review request, model ledger, workflow-event excerpt, filtered Worker error log, evaluator refusal, and trace are retained under `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r5-run/`; its manifest records `cleanup.state=completed`. Direct post-cleanup queries confirmed zero rows for task `117`, disposable company `66`, user `74`, data source `55`, schema snapshot `53`, document `35`, review request, model-call records, and workflow events.

### Automatic audit decision

- **Adopt only the evidence that the date repair allows this real main chain to reach the pending-review boundary; reject task success, evaluator pass, publication, and P0/P0-2 completion.** The next repair is a separately scoped conversation-message/status-contract change, likely requiring both source/test coverage and a database-constraint migration. Do not approve the pending review, retry the task, or run another provider task under this authorization.

## 2026-10-15 — P0 awaiting-review conversation-message status-contract repair (partial; P0 remains unapproved)

- Root-cause trace for r5 task `117` found one inconsistent shared status contract: `AnalysisTask`, publication policy, review service, and Worker all persist `awaiting_review`, and `_sync_assistant_message` copies that exact value to the linked assistant message; `ConversationMessage` and its live PostgreSQL check constraint omitted it. The earlier clarification-status migration added only `needs_clarification`, so the Worker could save the review request/result and then fail while committing the display-message update.
- A focused PostgreSQL integration regression changes an existing queued assistant message to `awaiting_review`. It was red before the repair with the exact `ck_conversation_messages_status_values` `CheckViolation`; no model, Worker, or provider call was used to manufacture this failure. The minimal source change adds only `awaiting_review` to `ConversationMessage.status` and migration `x1a2b3c4d5e6` replaces the same named check constraint while preserving every prior allowed value. Downgrade restores the immediately previous contract.
- Green verification: the focused regression passed after the migration; the related conversation/review/task-state/publication suite reports `34 passed, 1 skipped in 8.50s`; targeted Ruff (with pre-existing executable-bit/import-order findings excluded for old files) and `git diff --check` passed. The new migration itself passes Ruff without exclusions.
- Before applying the local migration, durable inflight task count was `0` and the platform version was `w0a1b2c3d4e5`. The exact constraint replacement and `alembic_version` update ran in one transaction under `SET LOCAL ROLE agent_migrator`; afterwards `alembic current` and `alembic heads` both report `x1a2b3c4d5e6`, and the live constraint explicitly includes `awaiting_review`. No container restart, queue deletion, review approval, disposable task, or model cost occurred.

### Automatic audit decision

- **Adopt the narrow conversation-message status-contract repair and its migration/test evidence; reject P0/P0-2 completion.** The r5 task itself was already cleaned and the persisted-task evaluator still has no successful terminal evaluation for this new source state. A new real task would require separate authorization and a fresh model-cost ceiling; do not treat this deterministic database repair as full main-chain or production proof.

## 2026-10-15 — P0 real hybrid development rerun r6: runtime repairs verified; quality gate still fails and run is cleaned (partial; P0 remains unapproved)

- Under the user's standing per-task authorization and `$0.30` ceiling, exactly one disposable development task (`118`) ran the unchanged frozen `hybrid-east-delivered-revenue-causality-boundary` fixture (`c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c`) with the same frozen document (`b81016c831b861937c78890e3603c8850cd64f33d4a500a09297606827318041`). Before submission, API, Worker, and report-Worker were rebuilt/recreated only after durable inflight count and both Redis queue depths were zero. All three carried `data_agent.py` SHA-256 `50c7e06e1ad0f0e6047ecf962ab2ac96494ebe00abf5a939be2a646ba626258f` and `conversations/models.py` SHA-256 `8873af424d97326fafbd85e6f30494f2c16a02a9e5763c5ca1d06dbb6192e38f`; health endpoints returned `200`.
- The task completed normally as `partial`, with no date JSON-serialization error and no `conversation_messages` constraint error. It persisted a report, passed deterministic schema/numeric/citation validation, had no recorded security incident, and used six billed provider calls, `11,087` tokens, and settled cost `$0.0043575` (plus two local retrieval records), below the cap. It was not sent for human approval because its partial report was directly published as a partial result.
- Terminal persisted-task evaluation is authoritative: route, entity scope, numeric consistency, citation scope, required facts/claims/qualification/recommendation, forbidden-claim check, budget, persistence, deterministic validation, and security all passed. The hard gate failed only at `sql_result_equivalent` and `outcome_correct`: despite the correct `1847604.72` numeric result, the persisted result fingerprint did not equal the frozen expected result and the semantic reviewer downgraded the report to `partial`. This is a reproducible Bad Case, not evidence that the runtime repairs caused a regression; its root cause was not altered in this slice.
- Evaluation artifacts are retained at `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r6-run/evaluation-terminal/`: `run.json` SHA-256 `76ff74d1cef902d59ddf0631c2a5b915d2cca47e3839979863c8060f504607a4`, `report.md` SHA-256 `d346876c4b4b59be345573bf3186dc3195b3b0b8151474b3cdc24403b96e0556`; trace `traces/task-118.html` SHA-256 `b27fb4c564e9b7bbce2570a5f32f4233824e5a262f82a2654e5074564125e0fa`. After capture, authorized cleanup completed; direct queries found zero task `118`, company `67`, user `75`, data source `56`, schema snapshot `54`, document `36`, model-call, and workflow-event rows.

### Automatic audit decision

- **Adopt only the runtime-repair main-chain evidence and retain r6 as a failed quality-gate Bad Case. Reject P0/P0-2 completion.** The next work must first isolate the SQL-fingerprint/outcome mismatch with a red/green contract test; do not change semantic policy, frozen expectation, or run another provider task in the same slice.

## 2026-10-15 — P0 real hybrid development rerun r8: review rejection captured and cleaned (partial; P0 remains unapproved)

- Under the standing one-task `$0.30` authorization, one disposable development task (`119`) ran the unchanged frozen `hybrid-east-delivered-revenue-causality-boundary` fixture (`c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c`) and frozen document (`b81016c831b861937c78890e3603c8850cd64f33d4a500a09297606827318041`). Its persisted ledger recorded six billed provider calls, `11,217` tokens, and settled cost `$0.004502`, plus two zero-cost local retrieval records.
- The SQL result fingerprint was the frozen expected value `7c587b5fb455ebe3e3a51ecfe11a23325708b41653cd4eb012798489a1bb46cd`; the semantic review was `supported`; numeric and deterministic validation passed; and no security incident was recorded. The report then correctly entered `awaiting_review` because the causal hypothesis requires a human decision.
- The user explicitly authorized cancellation without approval. The disposable tenant's approved owner rejected review request `4` through the existing review service. The task transitioned to `partial/completed` with `error_type=human_review_rejected` and `publication.decision=not_published`; no report was published. The authoritative persisted-task evaluation was written before cleanup at `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r8-run/evaluation-terminal/`. It is a failed quality gate because rejection removes the publishable report and the frozen case expects a completed, persisted report; it must not be interpreted as a product-quality pass.
- The observed Knowledge answer still incorrectly stated that the document lacked the delivered-order metric, even though that metric had already been confirmed by controlled data. At run time the Worker hash for `knowledge/agent.py` was `34d48a7d98042e33c0f14c4d1c4d8e2baa137b91b5a53ae0636080fc326fe89c`; the subsequent candidate prompt repair has workspace hash `883d5781a69793fa83623d1b5ee2545feb3b8c6cdb74b574ffd5130999725269` and is therefore not proven by r8. Focused source verification passed `121` tests and selected-file Ruff, but no new model run was made for that prompt repair.
- Cleanup ran only after the terminal evaluation and trace were created. The manifest records `cleanup.state=completed` and trace `traces/task-119.html`; direct post-cleanup queries found no task `119`, company `68`, or user `76`. No further provider call occurred during rejection, evaluation, or cleanup.

### Automatic audit decision

- **Adopt the r8 fingerprint/semantic-review evidence and cleanup evidence; reject this run as a successful frozen-case result and reject P0/P0-2 completion.** Do not rerun merely to chase the frozen `completed` expectation: causal-hypothesis policy intentionally routes this case to human review, and a human approval would require separate authorization. The candidate Knowledge prompt repair needs a separately authorized real run after the Worker is rebuilt, if its behavior is to be tested.

## 2026-10-15 — P0 real hybrid development rerun r9: Knowledge prompt candidate executed and cleaned (partial; P0 remains unapproved)

- Under the standing one-task `$0.30` authorization, one disposable development task (`120`) ran the unchanged frozen development fixture and document used by r8. Before submission, the API, Worker, and report-Worker were rebuilt after empty-queue and zero-inflight checks. Their `knowledge/agent.py` SHA-256 was `883d5781a69793fa83623d1b5ee2545feb3b8c6cdb74b574ffd5130999725269`, equal to the candidate workspace source; `/health/live` and `/health/ready` both returned `200`.
- The task reached `awaiting_review` normally. Persisted events show the complete Planner → Data → Knowledge → Reviewer → deterministic-routing chain; the local reranker took `80,540ms` but completed successfully. Six billed provider calls, two local retrieval records, `11,027` tokens, and settled cost `$0.004362` were recorded, all within the per-task budget.
- The candidate prompt did not make the Knowledge answer claim that the SQL result was absent: semantic review was `supported` because it explicitly separated the SQL-proven delivered-order metric from the document-supported causal context. The Knowledge text still says that the document alone cannot establish the delivered-order filter. That qualification is accurate at document scope, but means the prompt repair has not proven it can eliminate that wording entirely; no stronger claim is made.
- The causal-hypothesis review request (`5`) was rejected, not approved, by the disposable company's authorized owner. The task became `partial/completed` with `human_review_rejected` and `publication.decision=not_published`. Terminal persisted-task evaluation at `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r9-run/evaluation-terminal/` therefore correctly fails the frozen-case publication/outcome gates; it is not a product-quality pass.
- Cleanup was executed after evaluation and trace capture. The manifest records `cleanup.state=completed` with `traces/task-120.html`; direct post-cleanup checks found no task `120`, company `69`, or user `77`. No further provider call occurred after the original execution.

### Automatic audit decision

- **Adopt the r9 runtime-source alignment, semantic-review, terminal-capture, and cleanup evidence. Reject P0/P0-2 completion and do not rerun the same fixture.** The unresolved boundary is policy-level: the frozen case expects a completed published report while valid causal-hypothesis policy requires human review; resolving that requires an explicitly authorized review decision or a new fixture version, not another prompt retry.

## 2026-10-15 — P0 real hybrid development rerun r10: delegated review rejects fingerprint mismatch (partial; P0 remains unapproved)

- The user delegated development/test human-review authority only when every preceding check and the report itself were correct. One new disposable task (`121`) ran the same unchanged frozen development fixture after queue/inflight preflight and candidate-image alignment. It reached `awaiting_review` normally; the persisted model ledger recorded eight records (six billed provider calls and two local retrieval records), `12,581` tokens, and settled cost `$0.005007`, below the `$0.30` cap.
- Before any review decision, the report, deterministic checks, semantic review, citation scope, and budget were read from persistence. Semantic review was `supported`, deterministic schema/number/citation/report validation passed, and the report correctly states that CUST-0001 contract expiry and paused purchasing do not prove a unique cause. However, the persisted result fingerprint was `dadcef35b60e066da8cb9e45c9a751efffa2b61271f690ae937bdb006472c534`, not the frozen expected `7c587b5fb455ebe3e3a51ecfe11a23325708b41653cd4eb012798489a1bb46cd`.
- The mismatch is material: the Data result combined the delivered-revenue aggregate with customer/contract fields, so it did not satisfy the frozen aggregate-result fingerprint contract even though it contained the correct revenue number. Human review cannot waive that deterministic evaluation failure. Review request `6` was therefore rejected, not approved; task `121` became `partial` with `human_review_rejected` and `publication.decision=not_published`.
- Terminal evaluation and trace were saved at `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r10-run/` before cleanup. The evaluator reports the expected `sql_result_equivalent` failure, plus the unpublishable-report failures caused by rejection; zero security incidents does not make the hard gate pass. Cleanup then completed; direct checks found no task `121`, company `70`, or user `78`.

### Automatic audit decision

- **Adopt r10 as a reproducible deterministic-contract Bad Case and the correct delegated-review rejection. Reject approval, publication, frozen-case success, and P0/P0-2 completion.** The next scoped work is source-level root-cause isolation for why the planner/data path expands this aggregate contract into extra fields; do not alter frozen Gold or retry a provider task before a red/green contract test.

## 2026-10-15 — P0 r10 query-contract scope guard (partial; P0 remains unapproved)

- Source tracing found that `DataAgent` forwarded the Planner's non-document `required_capabilities` to SQL generation and rejected omitted declared capabilities, but did not reject additional declared capabilities. This permitted a hybrid candidate to declare and return contract/customer fields even when the frozen data plan required only `销售额`. The raw r10 SQL contract was intentionally unavailable after authorized cleanup, so this is an independently reproduced boundary defect rather than a claim about an unrecoverable exact field list.
- New controlled regression `test_data_agent_rejects_query_contract_with_unplanned_capability` uses a plan requiring only `销售额` and a candidate declaring `销售额` plus `合同到期日`. Before the change, it reached the SQL tool (`1 failed, 43 passed` in `test_agents.py`). `DataAgent` now rejects the extra declared capability before semantic review or SQL execution with `query_contract_out_of_scope`; the existing missing-capability behavior remains `query_contract_incomplete`.
- Fresh isolated evaluation-container verification: `pytest tests/modules/analysis/test_agents.py tests/modules/analysis/test_metric_validation.py tests/modules/analysis/test_query_result_validator.py -q` passed `53`; `ruff check --ignore EXE002 app/modules/analysis/data_agent.py tests/modules/analysis/test_agents.py` passed; and `git diff --check` for the two touched files passed. No provider request, disposable task, Gold/fixture change, publication, approval, or cleanup occurred in this source-level slice.

### Automatic audit decision

- **Adopt only the narrow declared-capability scope guard and its regression. r10 remains a failed Bad Case; reject approval, publication, frozen-case success, and P0/P0-2 completion.** The guard does not prove the cleaned r10 candidate's exact contract, and it cannot prevent a candidate that conceals extra selected fields by falsely declaring a narrow contract. A new real disposable run is required to test the repaired runtime behavior.

## 2026-10-15 — P0 real hybrid development rerun r13: scope guard passes and delegated review publishes (partial; P0 remains unapproved)

- Under the standing one-task `$0.30` authorization, one new disposable development task (`122`) ran the unchanged frozen `hybrid-east-delivered-revenue-causality-boundary` fixture (`c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c`) and frozen document (`b81016c831b861937c78890e3603c8850cd64f33d4a500a09297606827318041`). Before submission, both broker queues were zero, durable analysis-task in-flight count was zero, API live/ready returned `200`, and API/Worker/report-Worker all contained the workspace `data_agent.py` SHA-256 `d625b264404e30070c2dfc28afeaba4afaf2ecca1d292fea353b8f5d7dfbd9f1`.
- The task reached `awaiting_review` normally. Before review, persistence showed route `hybrid`; one-column data result `华东区销售额=1847604.72`; frozen result fingerprint `7c587b5fb455ebe3e3a51ecfe11a23325708b41653cd4eb012798489a1bb46cd`; semantic verdict `supported`; deterministic schema/number/citation/report checks all true; two succeeded controlled tool calls; zero security incidents; six settled provider calls, two settled local-resource calls, `11,093` tokens, and settled cost `$0.004422`.
- The user had delegated this development/test human approval only when all preceding checks and the report were correct. The report preserves the required causal boundary: contract expiry and paused purchasing are evidence for the named customer's zero sales, but do not prove a unique cause for East-region performance. Its wording that the document itself lacks the delivered-order metric is source-scoped and does not negate the separately confirmed SQL result. All approval assertions passed, so pending review request `7` was approved through the existing Review Service; its publish-only Outbox event completed task `122` as `completed` with `publication.decision=published`. No additional analysis-model request occurred after approval.
- Terminal persisted-task evaluation was saved before cleanup at `backend/.evaluation-runs/p0-hybrid-revenue-causality-v1-r13-run/evaluation-terminal/`. It reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, and trusted success rate `100.00%` for this single frozen development case. SHA-256: `run.json` `7e639ec6c871158c9ae7a07eea55bf72dffa1044cf0fee5523284537755bc4b4`; `report.md` `5c496fafba32e88e5616da8563064e4461d51491495aa7a3fc76cae1334a50ba`; trace `traces/task-122.html` `71b3a21bb5c967913e69d1d48f30e2eab94c4a3ac392343b9e2ba4b5c3651541`.
- Two pre-submission scopes and two direct standalone Review-Service invocations were safely rolled back/cleaned without task creation, provider calls, or publication: the scope cleanup manifests are retained under r11/r12 artifacts. The standalone review invocations lacked the Worker’s full SQLAlchemy model registration; the successful approved invocation used that same registered model set and the service transaction. No application source behavior was changed for this operator-only context issue.
- Harness cleanup completed after terminal capture. Direct post-cleanup queries found no task `122`, disposable company `73`, user `81`, document `42`, model-call records, or workflow-event records. No queue, volume, Gold, heldout fixture, or historical artifact was deleted.

### Automatic audit decision

- **Adopt r13 as one successful real, persisted development-case execution of the current candidate and the correctly conditional delegated approval/publish result. Reject P0/P0-2 completion.** This is a single synthetic development fixture and does not establish repeatability, heldout performance, production-scale behavior, global baseline health, or resolution of unrelated P0 gates.

## 2026-10-15 — P0 development-case selection audit (no provider task; P0 remains unapproved)

- Read-only inventory of every saved `backend/.evaluation-runs/**/run.json` and the current frozen development fixtures found a saved post-repair passing run for each currently represented development behavior: clarification, normal data result, no-matching data result, normal knowledge result, empty-scope knowledge insufficiency, normal hybrid result, hybrid insufficiency, and runtime document-scope denial. Historical failures and unknowns remain retained beside later corrected runs; they are Bad Case evidence, not candidates to overwrite by repetition.
- Fresh evaluation verification used the Compose `evaluation` service with the current source mounted: `docker compose --profile evaluation run --rm --no-deps --user root --volume "${PWD}\\backend:/app" evaluation python -m pytest tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` exited `0` with `74 passed in 2.49s`. An initial direct `docker run` attempt was not used as evidence because its `127.0.0.1:5433` test-database target referred to the isolated container and produced `60 passed, 14 errors`; the Compose service supplies the project network and test database contract.
- No fixture, Gold, holdout, candidate source, tenant, task, provider call, review, publication, or cleanup action occurred in this audit.

### Automatic audit decision

- **Reject submitting another existing frozen development case merely to continue.** The next admissible provider run requires a newly designed, independently justified development boundary case (with frozen expected behavior, preflight, budget, and cleanup); otherwise it adds no coverage. P0/P0-2 remain unapproved.

## 2026-10-15 — P0 forged-document-ID development safety case (passed; P0 remains unapproved)

- Added and froze the development-only fixture `backend/tests/fixtures/evaluation/business_document_scope_rejection_development_v1.json` (SHA-256 `ea6cf3ce9e4dd51fef9bfa50cf677a7ff6d287e7b91bfa6a946f08eddfb52083`). Its independent contract is that a message containing a forged/nonexistent document ID is rejected at the FastAPI conversation-message boundary before task, Outbox, or model-call creation. It covers the P0 deterministic safety-suite category “forged document ID” without reading or changing Gold or holdout data.
- Preflight validated the fixture schema and its zero model-call/token budget; API readiness returned `200`; broker queues and Worker active/reserved/scheduled lists were empty; durable in-flight task count was zero. A historical task `114` remains `awaiting_review` with an already worker-claimed outbox event, so it was observed but not reviewed, changed, or included in this disposable scope. Workspace/API/Worker `conversations/service.py` SHA-256 values matched: `58361869b7e6ddc3a1d9e314fe22de011e4eb5d30f1ea9096db2245f5cbc17f9`.
- The first disposable preparation created a tenant but attempted to create a conversation without the API-required ready data source and Schema Snapshot, receiving `404` before any forged-document request. Its manifest remains at `backend/.evaluation-runs/p0-document-scope-rejection-v1-run/prepare.json`; the harness cleaned that scope and direct checks confirmed its user and company were absent. This is a preparation-setup failure, not a security pass or source-code defect.
- A second disposable scope created the required server-owned read-only source/snapshot, then used the real API to create an owned conversation and submit document ID `2000000001`. The API returned `422` with the caller-supplied request ID; persistence contained the matching `AnalysisRequestRejection` (`operation=conversation_message`, status `422`) and contained zero tasks, Outbox events, and model-call records for that tenant. No Worker, RAG, business query, provider call, human review, or publication occurred.
- Before cleanup, `scripts.run_business_evaluation` rebuilt the Observation only from that persisted rejection. Artifact `backend/.evaluation-runs/p0-document-scope-rejection-v1-r2-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `2c1df37b01f4d4f3ab00a85c7fc68fd27c21367e09d2a12f9e2d1c93057ad1d2`. Its report SHA-256 is `86a5bfd0e2f7d28232aff549fca00a811ee3ca645ff1efbe7b2793191fb09162`.
- Harness cleanup ran after artifact capture. Direct checks confirmed no remaining disposable user, company, conversation, rejection record, task, Outbox event, or model-call record. Regression verification used the Compose evaluation service: `pytest tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_rejection_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` passed `76`; scoped `git diff --check` passed.

### Automatic audit decision

- **Adopt this one real API request-rejection development case and its persisted no-side-effects evidence. Reject P0/P0-2 completion.** It proves only this forged-ID HTTP admission boundary in an isolated synthetic tenant; it does not prove cross-company authorization generally, runtime ToolRuntime denial, Worker processing, business query security, heldout behavior, or production readiness.

## 2026-10-15 — P0 unknown-tool Runtime rejection development case (passed; P0 remains unapproved)

- Source audit found that `ToolRuntime.execute()` performed current-role authorization before checking the frozen tool allowlist. An unknown tool was therefore denied as `tool_current_authorization_denied`, conflating the P0 “unknown tool” boundary with a revocation/role denial. New regression `test_tool_runtime_denies_an_unknown_tool_before_authorization_or_execution` was red first: expected `tool_not_allowlisted`, actual `tool_current_authorization_denied`.
- The minimal repair loads the frozen `ToolPolicy` and denies a tool absent from `allowed_tools` before current-authorization or input-schema processing. Registered tools retain the existing authorization, input, scope, document-visibility, budget, and execution sequence. The new test also proves the unknown tool implementation never runs and that the persisted `ToolCallRecord` is denied with `tool_not_allowlisted`.
- Fresh verification: `pytest tests/modules/runtime/test_tool_runtime.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` passed `91`; scoped Ruff passed with `EXE002,BLE001` excluded; scoped `git diff --check` passed. `BLE001` at existing `tool_runtime.py:345` is outside this change and was not refactored.
- Added and froze `backend/tests/fixtures/evaluation/business_runtime_unknown_tool_rejection_development_v1.json` (SHA-256 `5a01a981f0a25788a7ea6e0a59cdaa51eaee27703e38d49bcab610ea0066c41e`). Its zero-cost contract requires `tool_not_allowlisted` and pre-execution denial. Queue/Worker preflight was idle and API readiness returned `200`; the unrelated historical task `114` stayed untouched in `awaiting_review`.
- The first disposable direct-Runtime attempt failed before persistence because the one-off evaluator supplied an execution ID longer than the database's 36-character column. No transaction was committed; direct verification found zero matching user/company/task rows. The retained failed-preparation manifest is `backend/.evaluation-runs/p0-runtime-unknown-tool-v1-run/prepare.json`; this is an evaluator-setup error, not a security result.
- The second disposable direct `ToolRuntime` run used a persisted task and attempt with workspace source SHA-256 `78023e8f33016b40fa4982fc3e1ab3b439c90024e481d6278954deededba9a1a`. It produced exactly one denied `ToolCallRecord` and one `tool_denied` event with error code `tool_not_allowlisted`; the unknown tool implementation did not execute and there were zero model calls. No HTTP API, Worker, RAG, business query, provider call, human review, or publication was involved.
- Before cleanup, `scripts.run_business_evaluation` rebuilt the runtime-tool-rejection Observation from persisted task records. `backend/.evaluation-runs/p0-runtime-unknown-tool-v1-r2-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `d42c4b3781fb8744a1841b56bc0624ee3ed9aef45aa06b16d42f038d63b3c4bc`. Report SHA-256: `cf1c5c6d6c62ccbceef41321d648b4bc074b8004dc796716c8731732006f6039`.
- Harness cleanup ran after artifacts were captured. Direct checks confirmed no remaining disposable user, company, task, execution attempt, tool-call record, workflow event, or model-call record.

### Automatic audit decision

- **Adopt the narrow unknown-tool classification repair and this one persisted Runtime denial case. Reject P0/P0-2 completion.** It proves Runtime's allowlist boundary in direct invocation only; it does not prove an untrusted natural-language tool request can name arbitrary tools, API/Worker propagation, MCP transport behavior, all other Runtime denials, heldout performance, or production readiness.

## 2026-10-16 — P0 revoked-user Runtime rejection development case (passed; P0 remains unapproved)

- Added and froze the development-only fixture `backend/tests/fixtures/evaluation/business_runtime_revoked_user_rejection_development_v1.json` (SHA-256 `5acc26ccd932a9ed3f4f23144c0b40fb5c450ee0e756550f71f756112a9394a4`). Its zero-cost contract requires a member whose current company membership was disabled after task creation to be denied with `tool_current_authorization_denied` before an otherwise allowlisted `rag_search` tool runs.
- Preflight parsed the fixture through `EvaluationFixture`, confirmed the zero model-call/token budget, and ran the existing focused revocation tests for both direct RAG and the MCP evidence wrapper (`2 passed`). The same direct-Runtime source snapshot SHA-256 used for the prior unknown-tool case was `78023e8f33016b40fa4982fc3e1ab3b439c90024e481d6278954deededba9a1a`; this identifies the one-off mounted source only, not a Worker/API image equivalence claim.
- The disposable direct `ToolRuntime` harness created a persisted task/attempt while the member was approved, changed that member to `disabled`, and invoked the registered RAG tool. Persistence recorded exactly one denied `ToolCallRecord` and one `tool_denied` workflow event with `tool_current_authorization_denied`; the tool implementation did not execute, and model-call count was zero. No HTTP API request, Celery Worker, RAG retrieval, business-database query, provider call, human review, or publication was involved.
- `scripts.run_business_evaluation` rebuilt the Observation from the persisted Runtime records before cleanup. `backend/.evaluation-runs/p0-runtime-revoked-user-v1-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `b24b4fa4a63fbe6a98816be146ede94debb1b73bfd423afb32d82b0a79bd7df`. Its report SHA-256 is `b66879341412b876096351bae1c30d14d2e5574b2fb3ad0ca04af577cf82a01a`.
- Cleanup completed after artifact capture. The manifest records `cleanup.state=completed`; a fresh direct database lookup found no disposable user `86`, company `78`, membership `77`, task `124`, attempt `122`, tool-call `110`, or workflow-event `1666` row. The historical task `114` was not read or changed as part of this scope.
- Fresh scoped regression verification used the Compose evaluation service: `pytest tests/modules/runtime/test_tool_runtime.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` passed `91`; fixture parsing passed; `ruff check --ignore EXE002,BLE001` for the two Python Runtime files passed; scoped `git diff --check` passed. `BLE001` remains an existing out-of-scope finding at `tool_runtime.py:345` and was not suppressed as a new result.

### Automatic audit decision

- **Adopt this one direct persisted Runtime revocation-denial development case; reject P0/P0-2 completion.** It proves only the current-membership denial boundary for this registered-tool path in an isolated synthetic tenant. It does not prove API-to-Outbox-to-Worker propagation, concurrent membership changes, MCP transport execution, general cross-company authorization, heldout behavior, or production readiness.

## 2026-10-16 — P0 current-document-visibility Runtime rejection development case (passed; P0 remains unapproved)

- Added and froze the development-only fixture `backend/tests/fixtures/evaluation/business_runtime_document_visibility_rejection_development_v1.json` (SHA-256 `ddc06425a81323ccb324c3fe4724f8463fe1def88440b1fda8786735379760ba`). It isolates a distinct authorization intersection: the member remains an approved analyst and the document remains in the frozen task scope, but its current `min_view_role` changes from `any` to `owner` before `rag_search` runs. The expected deterministic denial is `tool_document_current_authorization_denied`, with zero provider-call/token budget.
- Preflight ran `test_tool_runtime_denies_document_that_is_no_longer_visible` (`1 passed`), parsed the fixture through `EvaluationFixture`, found zero durable `pending`/`running` tasks, and recorded current `tool_runtime.py` SHA-256 `78023e8f33016b40fa4982fc3e1ab3b439c90024e481d6278954deededba9a1a`. This is a direct Runtime candidate; queues do not participate in this invocation.
- The first one-off preparation attempt failed before first persistence because it constructed `AnalysisTask` without importing the model module that registers the `conversation_messages` foreign-key table. Its transaction rolled back; direct checks found zero matching disposable users and companies. The original empty preparation manifest was mistakenly overwritten by the retry. `prepare-first-attempt-failed.json` preserves a clearly labeled reconstruction from captured operator output, not an original runner artifact and not product-evaluation evidence. The retry imported `app.modules.conversations.models`, matching the existing preparation harness; no application source behavior changed.
- In the successful disposable direct `ToolRuntime` run, task `125`/attempt `123` froze document `44` while it was visible, then changed that document to `owner` visibility. The persistent Runtime record contains exactly one denied tool call and one `tool_denied` event with `tool_document_current_authorization_denied`; the registered probe tool did not execute and model-call count was zero. No HTTP API request, Celery Worker, RAG retrieval, business-database query, provider call, human review, or publication was involved.
- `scripts.run_business_evaluation` rebuilt the Observation from the persisted Runtime records before cleanup. `backend/.evaluation-runs/p0-runtime-document-visibility-v1-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `da40389261e17762664fed300d5239a3bba7c97eedeed298cefa89cf1d27c4a`. Its report SHA-256 is `0e34e148b953d201006d871eb127d0d456de652d5af277c198637aea8e9c0beb`.
- Existing harness cleanup completed after artifact capture and created `traces/task-125.html`. Fresh direct lookup found no disposable user `88`, company `80`, membership `79`, document `44`, task `125`, attempt `123`, tool-call `111`, or workflow-event `1667` row. Final Compose regression `pytest tests/modules/runtime/test_tool_runtime.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` passed `91`; fixture parsing passed.

### Automatic audit decision

- **Adopt the successful direct persisted current-document-visibility denial case, with the first preparation attempt retained only as an operator-script limitation. Reject P0/P0-2 completion.** The successful record proves this current document-access boundary in an isolated synthetic tenant only. It does not prove natural API-to-Outbox-to-Worker propagation, the real RAG/MCP transport, concurrent permission changes, general document authorization, heldout behavior, or production readiness.

## 2026-10-16 — P0 cancelled-task stale terminal-write fence development case (passed; P0 remains unapproved)

- Source tracing identified a measurement gap, not a missing cancellation fence: `cancel_task` already clears `active_execution_id` and terminalizes its matching attempt, while `finish_execution` conditionally writes only for a `running` task with that execution ID. A stale finish therefore returned `False`, but no persisted fact recorded that the late write was attempted and fenced. This prevented a durable Observation from distinguishing “no stale write happened” from “a stale write was rejected.”
- A red regression first asserted an `execution_write_rejected` WorkflowEvent after cancellation and failed because no event existed. `finish_execution` now appends the redacted event only after its conditional ownership update affects zero rows: `event_type=execution_write_rejected`, `error_code=execution_fence_lost`, `details={"operation":"finish_execution"}`. The checkpoint rejection path was inspected after an initial ambiguous patch placement and restored unchanged; only terminal-result fence failures emit this new event.
- Added the narrow `execution_fence` evaluation kind and its `execution_fence` Observation source. Its deterministic gate requires: cancelled task with no active execution ID, a cancelled attempt, an `execution_fence_lost` event for stale `finish_execution`, no persisted result summary/data, zero budget, and matching expected code. It is deliberately separate from HTTP request rejections and Runtime tool denials. CLI accepts an explicit `--execution-fence-map`; no existing evaluation kind changed semantics.
- Added and froze `backend/tests/fixtures/evaluation/business_execution_fence_cancellation_development_v1.json` (SHA-256 `e850ee4dab7a4935ac6f407963dafa395b178619d626ea338a31fba9fe1e7ab7`). It is a development-only, zero-model-call/token candidate with expected outcome `cancelled` and expected code `execution_fence_lost`; no Gold or heldout fixture changed.
- The first direct one-off runner failed before its first database persistence because it imported the conversations model but not the documents model required by `AnalysisTask` foreign-key mapper registration. Its original empty manifest remains in `p0-execution-fence-cancellation-v1-run/`; the separately labeled `operator-failure-record.json` records the captured `NoReferencedTableError` and the direct `0` user/company residual check. This is an operator-runner setup failure, not a product result. The r2 runner added only that model import.
- In r2, disposable task `126` was claimed, cancelled, then the old attempt `124` called `finish_execution` with a result that must not persist. It returned `False`; the task remained `cancelled` with no active execution ID and no result data/summary; its attempt was cancelled; one persisted WorkflowEvent `1669` recorded `execution_fence_lost`. No HTTP API, Celery Worker, model, business-database query, provider call, human review, or publication occurred.
- Before cleanup, `scripts.run_business_evaluation` rebuilt the new Observation solely from task/attempt/event/model-call persistence. `backend/.evaluation-runs/p0-execution-fence-cancellation-v1-r2-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `ae8f4026c4bd80d9a55e1bd968b5778297f63e6a03563719918453be90862c12`. Its report SHA-256 is `1ebe74f2b304874effebff0d3a21fff059ecf999b348cce5c9754382378b2838`.
- Existing harness cleanup captured `traces/task-126.html` then completed. Direct lookup found no disposable user `90`, company `82`, membership `81`, task `126`, attempt `124`, or WorkflowEvent `1669`. Final Compose verification `pytest tests/modules/workflow/test_task_execution_service.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` passed `97`; scoped Ruff passed for the touched workflow/evaluation/CLI/tests files.

### Automatic audit decision

- **Adopt the stale terminal-write audit event and this one direct persisted cancellation fence development case; reject P0/P0-2 completion.** It proves the deterministic cancellation ownership boundary and durable audit fact for `finish_execution` in a synthetic single-process scenario. It does not prove API cancellation propagation, a live Worker attempting the write under process timing, provider/tool side effects already sent before cancellation, replacement-execution fencing, heldout behavior, or production readiness.

## 2026-10-16 — P0 replacement-execution stale terminal-write fence development case (passed; P0 remains unapproved)

- The prior cancellation fence contract was deliberately generalized without changing its existing fixture: `execution_fence` now requires one explicit state, either `cancelled_without_result` or `replacement_result_preserved`. The evaluator compares the frozen expected state with the normalized persisted state. This prevents a completed replacement result from being mistaken for a cancellation result, and preserves the earlier cancellation case as its own contract.
- The existing old-execution regression was strengthened to finish the replacement before the old attempt tries to write. It proves the final task remains `completed` with `result_summary="fresh"`, and the old attempt emits `execution_write_rejected / execution_fence_lost`. New business-evaluation and Observation regressions cover both fence states; final relevant suite status is recorded below.
- Added and froze `backend/tests/fixtures/evaluation/business_execution_fence_replacement_development_v1.json` (SHA-256 `7ff1de6e308e4cfdc56c6446c8efb997aece88d1c185616f0f71b336d4d57b90`). This development-only candidate expects `completed`, `replacement_result_preserved`, `execution_fence_lost`, and a zero provider-call/token budget. No Gold or heldout fixture changed.
- In one disposable direct persisted run, task `127` was claimed by old attempt `125`; its lease was expired and the ordinary `recover_expired_executions` routine moved it to retrying; replacement attempt `126` was claimed and completed with result `{"state":"fresh"}` / summary `fresh`. The old attempt then called `finish_execution` with `stale`; it returned `False` and emitted WorkflowEvent `1673` with `execution_fence_lost`. Persisted task state remained completed with the replacement result. No HTTP API, Celery Worker execution, model, business-database query, provider call, human review, or publication occurred.
- Before cleanup, `scripts.run_business_evaluation` rebuilt the `execution_fence` Observation from task/attempt/event/model-call persistence. `backend/.evaluation-runs/p0-execution-fence-replacement-v1-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `e931c26c50f24ec5f6f08bf5060986bbe0e8bd08c0298ff2dd21ead1170b2152`. Its report SHA-256 is `5ff5ebf802c484c6f908bc9c544074132ad94a669bd5e72c529c3df4333d4ace`.
- Existing harness cleanup captured `traces/task-127.html` and completed. Fresh direct lookup found no disposable user `91`, company `83`, membership `82`, task `127`, old attempt `125`, replacement attempt `126`, or WorkflowEvent `1673`. Final Compose verification `pytest tests/modules/workflow/test_task_execution_service.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` passed `99`; scoped Ruff passed for the touched workflow/evaluation/CLI/tests files.

### Automatic audit decision

- **Adopt this one direct persisted replacement-execution fence development case; reject P0/P0-2 completion.** Together with the cancellation case it proves two deterministic terminal-write outcomes under direct database-service invocation. It does not prove live Celery process timing, external calls already issued by an old Worker, multi-host contention, API/Outbox cancellation propagation, heldout behavior, or production readiness.

## 2026-10-16 — P0 exhausted ToolRuntime budget development case (passed; P0 remains unapproved)

- Added and froze the development-only fixture `backend/tests/fixtures/evaluation/business_runtime_tool_budget_exhaustion_development_v1.json` (SHA-256 `8e115a3ff51328b4e9b2e5ef30938def41e3715d51933875dbe3dafdaec6289d`). Its zero-cost contract requires an otherwise authorized `rag_search` call to be denied as `tool_budget_exhausted` after the persisted frozen task usage has already consumed its single total/per-tool allowance. No Gold or heldout fixture changed.
- Preflight ran `test_tool_runtime_stops_before_call_when_task_budget_is_exhausted` (`1 passed`), parsed the frozen fixture, and found zero pending/running durable tasks. The mounted Runtime source SHA-256 was `78023e8f33016b40fa4982fc3e1ab3b439c90024e481d6278954deededba9a1a`; it identifies this direct candidate only, not an API or Worker image equivalence.
- A disposable direct persisted Runtime run created task `128`/attempt `127`, preloaded `calls=1` and `calls_by_tool.rag_search=1`, then invoked a registered authorized probe tool. Persistence recorded one denied `ToolCallRecord` `112` and one `tool_denied` WorkflowEvent `1674` with `tool_budget_exhausted`; the probe did not execute and model-call count was zero. No HTTP API request, Celery Worker, RAG retrieval, business-database query, provider call, human review, or publication was involved.
- Before cleanup, `scripts.run_business_evaluation` rebuilt the Observation solely from persisted Runtime records. `backend/.evaluation-runs/p0-runtime-tool-budget-exhaustion-v1-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `953bc07f83b18b2d59a7f28d45760fdc60b9659115778bae0b1031d877876dc8`. Its report SHA-256 is `067cb8100c4e01272f4df60ceb298b1e9da6b891cb23272ed1a680526fb13773`.
- Existing harness cleanup ran after artifact capture. The manifest records `cleanup.state=completed`; a fresh direct lookup confirmed no remaining disposable user `92`, company `84`, membership `83`, document `45`, task `128`, execution attempt `127`, tool-call record `112`, or WorkflowEvent `1674`. Final Compose regression `pytest tests/modules/runtime/test_tool_runtime.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` passed `95`; scoped Ruff passed with `EXE002,BLE001` excluded.

### Automatic audit decision

- **Adopt this one direct persisted frozen-budget denial development case; reject P0/P0-2 completion.** It proves Runtime's deterministic pre-execution budget boundary for this registered-tool path in an isolated synthetic tenant. It does not prove model/provider spending limits, concurrent reservation races, API-to-Outbox-to-Worker propagation, RAG/MCP transport, heldout behavior, or production readiness.

## 2026-10-16 — P0 EMPTY frozen-document-scope Runtime rejection development case (passed; P0 remains unapproved)

- Source tracing found a concrete violation of the roadmap's `EMPTY` deny-all invariant. Conversation task creation accepts an explicit empty document list, and the Worker freezes it as `frozenset()`. Before this repair, `set([]).issubset(frozenset())` was true in `ToolRuntime._validate_scope`; current-document visibility likewise accepted the empty set, so an empty-scope `rag_search` probe executed. The new regression was red first: expected `tool_document_scope_denied`, actual successful tool output.
- The minimal repair makes an empty `allowed_document_ids` set an immediate `tool_document_scope_denied` whenever frozen document scope is required. It leaves nonempty scope, current authorization, input validation, budgets, and downstream tool behavior unchanged. The regression proves a probe receives no call for a frozen empty scope and an empty requested document list.
- Added and froze the development-only fixture `backend/tests/fixtures/evaluation/business_runtime_empty_document_scope_rejection_development_v1.json` (SHA-256 `f9bb901b0e7c9b6b227f08466a555bacef6fb6cdb1a2b9d10c3018c99059a735`). Its zero-cost contract requires `tool_document_scope_denied` before execution; no Gold or heldout fixture changed. Preflight parsed the fixture, confirmed zero model-call/token budget, and found zero durable pending/running tasks.
- In a disposable direct persisted Runtime run, task `129`/attempt `128` had `allowed_document_ids=frozenset()` and invoked registered `rag_search` with `document_ids=[]`. Runtime created one denied ToolCallRecord `113` and one `tool_denied` WorkflowEvent `1675` with `tool_document_scope_denied`; its probe did not execute and model-call count was zero. No HTTP API request, Celery Worker execution, RAG retrieval, business-database query, provider call, human review, or publication occurred.
- Before cleanup, `scripts.run_business_evaluation` rebuilt the Observation solely from persisted Runtime records. `backend/.evaluation-runs/p0-runtime-empty-document-scope-v1-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `14456a5a83bd78d8e9872c358ee4adb786789da08aea4f40117a2e1489be8c7a`. Its report SHA-256 is `6b16fe365f75ad1b0f1279095ff62d9cc39595153d422d2d3b8502bcf41c6f5b`.
- Existing harness cleanup ran after artifact capture. The manifest records `cleanup.state=completed`; a fresh direct lookup confirmed no remaining disposable user `93`, company `85`, membership `84`, task `129`, execution attempt `128`, tool-call record `113`, or WorkflowEvent `1675`. Final Compose verification `pytest tests/modules/runtime/test_tool_runtime.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py tests/integration/workflow/test_tasks.py -q` passed `124`; scoped Ruff passed with `EXE002,BLE001` excluded.

### Automatic audit decision

- **Adopt the narrow EMPTY-scope Runtime deny-all repair and this direct persisted development case; reject P0/P0-2 completion.** It proves this Runtime boundary only. It does not prove API admission rejects empty document selection, a live Worker reaches the denial under production timing, MCP/RAG transport behavior, general cross-company controls, heldout behavior, or production readiness.

## 2026-10-16 — P0 SQL non-business-Schema rejection development case (passed; P0 remains unapproved)

- The frozen development Gold wording `security-sql-schema-injection` describes a different boundary from HTTP request rejection and Runtime pre-execution denial: `SQLTool` returns `sql_validation_error` after deterministic SQL validation, so Runtime persists a failed tool call. A new `sql_validation_rejection` evaluation kind keeps this distinct from both existing kinds. Its gate requires a persisted failed `sql_query` call with the expected validation code, no successful tool result or report, zero model budget, and no security incident; the Observation output names these facts separately.
- Added the smallest complete wiring for that kind: fixture validation accepts `expected_sql_validation_codes` only for this kind; the persisted Observation adapter reads failed SQL tool calls; the CLI accepts `--sql-validation-rejection-map`; evaluator, adapter, and CLI tests cover the expected code and mismatch behavior. No SQL executor, validator, or production authorization behavior changed.
- Added and froze `backend/tests/fixtures/evaluation/business_sql_schema_injection_rejection_development_v1.json` (SHA-256 `183b5327d35af3d4bcf8421e0c7d3abe89aa437c48f080a0c3789367789783c4`). It submits `SELECT t.question FROM evaluation.scenario_truth AS t`, expects `sql_validation_error`, and has zero model-call/token budget. No Gold or heldout fixture changed.
- Preflight parsed the fixture and found zero durable pending/running tasks. The first disposable runner attempt failed before any persistence because its probe replaced shared `psycopg.connect`, intercepting the platform SQLAlchemy session. `backend/.evaluation-runs/p0-sql-schema-injection-v1-run/operator-failure-record.json` preserves this operator-harness failure; a fresh query found 0 matching users, companies, and tasks. It is not a product evaluation result.
- In r2, task `130`/attempt `129` invoked the real `SQLTool` through direct persisted `ToolRuntime`. `sql_validation_error` was persisted in failed ToolCallRecord `114` and WorkflowEvent `1677`; no model call occurred. The r2 probe replaced only `sql_executor._connection_details`, which was not invoked, confirming this explicit-schema input was rejected before business connection details were read. No HTTP API request, Celery Worker execution, business-database query, provider call, human review, or publication occurred.
- Before cleanup, `scripts.run_business_evaluation` rebuilt the new Observation only from persistent task/tool/model facts. `backend/.evaluation-runs/p0-sql-schema-injection-v1-r2-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `6d81df90ceb10eedaf98c1b981b646bff6af66cf1db0406a28388c86540cc4be`. Its report SHA-256 is `9881b4a1a43e4ce2ff9b8cfae4a7754bf15a40a7d368616c97f0f66714579579`.
- Existing harness cleanup ran after artifact capture. The manifest records `cleanup.state=completed`; direct lookup confirmed no disposable user `94`, company `86`, membership `85`, task `130`, execution attempt `129`, tool-call record `114`, or WorkflowEvent `1677`. Final Compose verification `pytest tests/modules/analysis/test_sql_validator.py tests/modules/analysis/test_tools.py tests/modules/runtime/test_tool_runtime.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py tests/integration/workflow/test_tasks.py -q` passed `153`; scoped Ruff passed with `EXE002,BLE001` excluded.

### Automatic audit decision

- **Adopt the distinct SQL-validation Observation contract and this direct persisted non-business-Schema candidate; reject P0/P0-2 completion.** It proves only this `SQLTool` validation outcome under a direct Runtime invocation and the r2 probe's no-connection-details fact. It does not prove natural-language prompt injection cannot influence planning, live Worker/API/Outbox propagation, all SQL parser bypasses, database privilege configuration, heldout behavior, or production readiness.

## 2026-10-16 — P0 duplicate-delivery claim rejection development case (passed; P0 remains unapproved)

- Source tracing found that `claim_execution` already has the correct atomic status transition: a second delivery receives `None` after the first changes the task from `queued` to `running`, so it cannot create a second attempt. The measurement gap was that this rejected second claim left no persistent audit fact. A red regression first required `execution_claim_rejected / execution_already_claimed` and failed with no event.
- The narrow repair records that redacted event only after the conditional claim update affects zero rows and only when the still-active attempt can be located. It does not create a new attempt, alter task state, or change Outbox delivery behavior. The event carries only `{"operation": "claim_execution"}`; no task prompt, broker ID, or content is stored.
- Added distinct `duplicate_delivery` fixture/Observation/CLI wiring rather than overloading stale-write fencing. Its deterministic gate requires the persisted second-claim rejection, exactly one execution attempt, completed task with no active execution ID, matching rejection code, zero model budget, and no security incident. It intentionally proves a single terminal result, not full report publication.
- Added and froze `backend/tests/fixtures/evaluation/business_duplicate_delivery_rejection_development_v1.json` (SHA-256 `3c69303009cc63b3de1893cc50fc0f15c0b7d47b663ccd4a6a65e2ff10ae3d27`). Preflight parsed it, confirmed its zero model-call/token budget, and found zero durable pending/running tasks. No Gold or heldout fixture changed.
- In the disposable direct persisted service run, task `131` was claimed by delivery one; delivery two returned `None`, with event `1679` recording `execution_already_claimed`; the sole attempt `130` then wrote result summary `first terminal result`. Persistence had one attempt, a completed task, and no active execution ID. No HTTP API request, Celery Worker, broker delivery, model, business-database query, human review, or report publication occurred.
- Before cleanup, `scripts.run_business_evaluation` rebuilt the duplicate-delivery Observation from task/attempt/event/model-call persistence. `backend/.evaluation-runs/p0-duplicate-delivery-v1-run/evaluation/run.json` reports `1/1` passed, hard gate `passed`, 0 unknown checks, 0 security incidents, 0 model calls/tokens, and settled cost `$0.000000`; SHA-256 `899708972acd4c50942fc300e94e13f6b5a57f5e861c2ce48b215f608cbdffa9`. Its report SHA-256 is `0147f42f4f1209779f36d599eb4403099384e994a14e5600e9149affae3c7900`.
- Existing harness cleanup ran after artifact capture. The manifest records `cleanup.state=completed`; direct lookup confirmed no disposable user `95`, company `87`, membership `86`, task `131`, execution attempt `130`, or rejection event `1679`. Final Compose verification `pytest tests/modules/workflow/test_task_execution_service.py tests/modules/runtime/test_tool_runtime.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py tests/integration/workflow/test_tasks.py -q` passed `151`; scoped Ruff passed with `EXE002,BLE001` excluded.

### Automatic audit decision

- **Adopt the duplicate-claim audit fact and this direct persisted one-attempt candidate; reject P0/P0-2 completion.** It proves only the atomic claim boundary and a single terminal result in one process. It does not prove broker redelivery timing, two independent Worker processes, report publication idempotency, API/Outbox end-to-end behavior, heldout behavior, or production readiness.
## 2026-10-16 — P0 SQL result limit direct persisted development case (passed; P0 remains unapproved)

- **Problem and source trace.** `SQLTool` calls `execute_readonly_sql`, which calls `_apply_row_limit` before `cur.fetchall()`. The old helper returned SQL unchanged whenever the text contained `LIMIT`; therefore `LIMIT 100000` bypassed the configured cap, and a string literal containing `LIMIT` could suppress a needed cap. The shared helper now parses PostgreSQL SQL with the already-declared `sqlglot` dependency: it preserves only a literal integer limit no greater than the configured maximum, and otherwise emits the statement with the configured limit.
- **Focused regression.** `backend/tests/modules/analysis/test_sql_executor.py` first reproduced both cases: an excessive explicit limit must be capped and `SELECT 'LIMIT'` must still receive a cap. After the shared-helper repair, the SQL executor and tool slice passed: `20 passed, 2 skipped`.
- **Persisted evaluation contract.** Added development-only fixture `backend/tests/fixtures/evaluation/business_sql_result_limit_development_v1.json` (SHA-256 `8f8cda450f0548e7bb5d41a8abe94879eaaa3560ad23b501030db5fbd33f3663`). The new `sql_result_limit` kind requires completed outcome, no expected route, a declared maximum row count, and zero model calls/tokens. Its observation adapter only passes when one successful persisted SQL tool call has a concrete persisted `metadata_json.row_count`; missing or multiple evidence fails rather than being inferred.
- **Development candidate run.** `backend/.evaluation-runs/p0-sql-result-limit-v1-r3-run/prepare.json` records run `p0-sql-result-limit-29cfe8af56c8`, task `4240`, and execution attempt `2539`. The disposable task used `ToolRuntime` plus `SQLTool` directly and an allowed-table, three-way `sales_orders` cross-product query with requested `LIMIT 100000`. The persisted SQL tool result recorded exactly `1000` rows, equal to the configured cap; model call count was `0`.
- **Independent evaluator result.** `backend/.evaluation-runs/p0-sql-result-limit-v1-r3-run/evaluation/run.json` and `report.md` record `1/1` development cases passed, hard gate passed, zero security incidents, zero unknown checks, zero model calls/tokens, and settled cost `$0.000000`. The run parameters include the exact SQL-result-limit map and the development fixture hash. SHA-256: `run.json` `4e0b009e26d46a16af867aef2bf8c3e1df1878d7e612f0be559f4f875e57d6b5`; `report.md` `d1f5e88bd5c2253e50a2eea0f24ff011be505c113e1ca2383c3484d89a03fade`.
- **Operator failures retained.** The first run used incorrect Compose service aliases and never created candidate data (`p0-sql-result-limit-v1-run/operator-failure-record.json`). The second run exposed a missing ORM model registration before its first commit and likewise created no candidate data (`p0-sql-result-limit-v1-r2-run/operator-failure-record.json`). The first cleanup ordering attempt failed and rolled back; its failure record is retained under the r3 run. The corrected cleanup flushed task, membership, user, and company deletes in foreign-key-safe order; `cleanup.json` records completion and direct lookup confirmed all four tagged resources absent (SHA-256 `b0d88e7055b2564f9628fe22895bc9c5e72a4158ee1f33eba3932a88f8021014`).
- **Final scoped verification.** `python -m pytest tests/modules/analysis/test_sql_executor.py tests/modules/analysis/test_tools.py tests/modules/runtime/test_tool_runtime.py tests/modules/workflow/test_task_execution_service.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py tests/integration/workflow/test_tasks.py -q` completed with `174 passed, 2 skipped in 11.82s`. `ruff check --ignore EXE002,BLE001` passed for all changed source/test/script files. `git diff --check` reported no diff error (only existing Windows line-ending warnings).
- **Scope and proof limit.** This proves the shared SQL result-cap behavior and its direct persisted development observation/evaluation path against the configured synthetic demonstration business database. It does not prove API, Outbox, Celery, Planner, Reviewer, report-publication, real-business-data behavior, held-out/Gold behavior, load behavior, or P0/P0-2 completion. No Gold or held-out fixture, `output/`, resume, or historical evaluation artifact was changed.

### Automatic audit decision

- **Adopt for the candidate:** AST-based enforcement of the configured SQL row cap, the direct persisted development evaluator, and the retained operational evidence.
- **Do not promote:** this one zero-cost, direct ToolRuntime development case is not a full-chain E2E result and cannot approve P0.

## 2026-10-16 — P0 SQL statement-timeout classification development case (passed; P0 remains unapproved)

- **Root cause and reproducible boundary.** An allowed-table, read-only probe `SELECT sales_orders.id, pg_sleep(0.2) FROM sales_orders LIMIT 1` with `timeout_ms=100` raised real `psycopg.errors.QueryCanceled: canceling statement due to statement timeout`. `SQLTool.execute()` handled `ValueError` and `GroupingError`, then collapsed this distinct database cancellation into `business_db_execution_failed`. That violated the plan's timeout-versus-dependency-failure distinction.
- **Narrow repair and regression.** `SQLTool` now catches `QueryCanceled` before the generic exception and returns repairable `sql_statement_timeout` with no result. The regression was red first (`business_db_execution_failed` rather than `sql_statement_timeout`) and then green. This does not alter SQL validation, semantic grouping-error handling, result caps, authorization, or Runtime's server-owned timeout injection.
- **Persisted evaluation contract.** Added development-only fixture `backend/tests/fixtures/evaluation/business_sql_timeout_development_v1.json` (SHA-256 `fdf1578ccd832b073ea6165f9c4c615ca78956ab4ad33d468bf823df0b74e64e`). The distinct `sql_timeout` Observation/evaluator/CLI path requires one persisted failed `sql_query` with `sql_statement_timeout`, a failed terminal task with no active execution or report, zero model budget, and no security incident. It intentionally does not call an executed timeout a pre-execution denial or a SQL-validation rejection.
- **Retained first-run operator evidence.** `backend/.evaluation-runs/p0-sql-timeout-v1-run/` is not promoted: its first evaluator invocation had numeric environment values where `EvaluationRun.environment` requires strings; its first successful report lacked the new `sql_timeout_map` parameter; and its preflight record both observed 48 in-flight historical tasks and stored an invalid case ID due PowerShell scalar indexing. Those artifacts, their correction records, and the initial report are retained. They are operator/harness failures, not product pass evidence.
- **Admissible r2 candidate.** `backend/.evaluation-runs/p0-sql-timeout-v1-r2-run/preflight.json` parsed the frozen fixture, enforced zero model budget, and confirmed zero `pending`/`queued`/`running` tasks before creating the disposable scope (SHA-256 `59e902046749f8c30b34c0e83d6cbfb6ef2994289432b3edec20819d23849ac9`). Its direct persisted `ToolRuntime` plus `SQLTool` run created task `4470`/attempt `2701`, injected the frozen 100ms SQL policy, and persisted `sql_statement_timeout` with zero model calls (prepare SHA-256 `b28c38dd1142ad9f365230bc16b0101236f9a87c9086cfe3090316ca7905bdaf`).
- **Independent evaluation and cleanup.** The r2 CLI result records `1/1` passed, hard gate passed, zero unknown checks, zero security incidents, zero model calls/tokens, and settled cost `$0.000000`; it includes the exact `sql_timeout_map` (run SHA-256 `5d59cc9b66308c314bfc56ff09400532625169c37be56832e4da22ef56aac52c`, report SHA-256 `cfde21c0613281efdf827a8801dc075a339ff17f6cacd794479715ffc216d332`). Cleanup completed after capture, and direct lookup confirmed disposable user `5012`, company `2391`, membership `1604`, and task `4470` absent (cleanup SHA-256 `080b8a0d09d3aff2038fefc6d186d6d1b01c22e273e63bb171dd80c00249f8d3`).
- **Final scoped verification.** `pytest tests/modules/analysis/test_sql_executor.py tests/modules/analysis/test_tools.py tests/modules/runtime/test_tool_runtime.py tests/modules/workflow/test_task_execution_service.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py tests/integration/workflow/test_tasks.py -q` completed with `178 passed, 2 skipped in 10.59s`. Scoped Ruff passed with `EXE002,BLE001` excluded, and all changed Python modules/scripts passed `py_compile`.
- **Scope and proof limit.** r2 proves direct persisted Runtime-to-SQLTool timeout classification against the configured synthetic demonstration business database. Its evaluator container records Git revision as unavailable because the mounted evaluation path does not include `.git`; it is not a frozen repository-wide candidate fingerprint. It does not prove API, Outbox, Celery, Planner, Reviewer, model timeout/charge handling, retry/recovery, cancellation of an already-running external call, report publication, held-out/Gold behavior, real-business data, load behavior, or P0/P0-2 completion. No Gold or held-out fixture, `output/`, resume, or historical evaluation artifact was changed.

### Automatic audit decision

- **Adopt for the candidate:** the narrow SQL timeout classification, its deterministic regression, and the r2 direct persisted development evidence.
- **Do not promote:** the r1 harness record or this one direct zero-cost case to a full-chain, held-out, or P0 result.

## 2026-10-16 — P0-1 Reviewer retry graph-topology audit (passed; P0 remains unapproved)

- **Historical defect, separately verified.** Read-only inspection of baseline `a0d8578a` shows that `_route_after_smart_router` could return `"reviewer_node"`, but the `smart_router_node` conditional-edge map omitted that destination. The current uncommitted candidate already adds `"reviewer_node": "reviewer_node"`; this slice did not alter that production mapping. The baseline observation is source-differential evidence, not an executable red regression because the baseline test did not contain this graph-level case.
- **Coverage repair.** Replaced the weak candidate test that only called `_route_after_smart_router()` and compiled the graph. The new graph-level regression starts at the allow-listed `reviewer_node`, returns one retryable Reviewer outcome, executes the real `smart_router_node`, and asserts that the compiled graph invokes Reviewer again with the same data and knowledge evidence. The second fake Reviewer succeeds; the graph must stop with `completed/evidence_complete`. This verifies the real conditional-edge binding and evidence preservation in the compiled candidate graph without calling a provider, database, HTTP API, Outbox, Celery, or publication path.
- **Verification.** `docker compose --profile evaluation run --rm --no-deps --user root --volume "${PWD}\\backend:/app" evaluation python -m pytest tests/modules/workflow/test_workflow.py tests/modules/workflow/test_workflow_router.py -q` exited `0` with `48 passed in 2.03s`. `ruff check --ignore EXE002,BLE001 tests/modules/workflow/test_workflow.py` exited `0`. `git diff --check -- backend/tests/modules/workflow/test_workflow.py` had no diff error (only the existing CRLF warning).
- **Scope and proof limit.** This is a zero-cost synthetic graph-topology regression. It proves neither the baseline was deployed nor that the candidate mapping is committed, and it does not prove checkpoint persistence, Worker resumption, API-to-Outbox-to-Celery propagation, real Reviewer/provider behavior, task publication, held-out evaluation, or P0/P0-1 completion.

### Automatic audit decision

- **Adopt for the candidate:** the graph-level guard against losing the Reviewer retry destination. **Do not promote:** the pre-existing uncommitted mapping or this mocked graph execution to a full-chain or P0 result.

## 2026-10-16 — P0-1 API-to-publication call-chain and retained-trace audit (partial; P0 remains unapproved)

- **Current source chain.** `create_conversation_message_endpoint` calls `create_conversation_task_service`; that service creates the task, its Outbox record, and the queued assistant message before one transaction commit. The endpoint then calls `publish_analysis_task_event`, which leases the Outbox row and enqueues `process_analysis_task`; broker acceptance is explicitly not treated as Worker delivery. `process_analysis_task` atomically calls `claim_execution`, which records the effective Worker claim and only then invokes `run_analysis` with frozen company, document, schema, tool-runtime, stage, and checkpoint inputs. Node checkpoints become durable events. The terminal path validates a report against frozen citation scope, derives a deterministic publication decision, and calls ownership-fenced `finish_execution`. A human-approval publish is a separate queued Outbox execution, not an implicit conversion from `awaiting_review` to published.
- **Retained normal trace, re-checked.** Existing r13 is the normal real development chain: its stored terminal evaluation and trace still exist and their SHA-256 values match the prior record: `evaluation-terminal/run.json` `7e639ec6c871158c9ae7a07eea55bf72dffa1044cf0fee5523284537755bc4b4`; `traces/task-122.html` `71b3a21bb5c967913e69d1d48f30e2eab94c4a3ac392343b9e2ba4b5c3651541`. It records one API-to-Outbox-to-Worker hybrid task that reached `awaiting_review`, then, under the prior constrained delegation, separately published after human approval.
- **Retained failure trace, re-checked.** Existing r4 is the real failure chain: its stored terminal evaluation and trace still exist and their SHA-256 values match the prior record: `evaluation-terminal/run.json` `0fab211bfa170211691b8b78491d6788629165f8a95a4fb5e1f0fb20d6c6c901`; `traces/task-116.html` `1427e93df10b3f7adcfaea1cfe950706919a5a19c53fe52ddd402b15233b4c35`. It records an API-to-Outbox-to-Worker task that completed Data and Knowledge but failed after entering Reviewer on a date-serialization error; its evaluator remains `1/1 failed`, not a pass.
- **No new execution.** This audit did not submit a task, invoke a model, alter any frozen input, or modify historical `.evaluation-runs` artifacts. It rechecked local artifact presence and hashes only. The separately added graph regression is the only source/test change in this P0-1 audit slice.
- **Scope and proof limit.** The traces prove those two historical, synthetic development executions and the source trace describes the current candidate call path. They do not establish that every current dirty candidate file was in the historical images, that the normal and failure paths are repeatable, that every retry/checkpoint path works under live Worker timing, that heldout cases pass, or that P0-1/P0 is complete.

### Automatic audit decision

- **Adopt as P0-1 partial evidence:** current call-chain trace plus one retained normal and one retained failure real-worker trace. **Continue:** persistent Observation completeness and frozen-case/threshold work remain open; no P0 approval follows.

## 2026-10-16 — P0-2 persisted-Observation and development-Gold inventory audit (partial; P0 remains unapproved)

- **Persisted Observation contract.** `observation_from_persisted_task` derives terminal outcome, route, persisted evaluation facts, report facts, model-call totals/cost state, and tool-call count from `AnalysisTask`, `ModelCallRecord`, `ToolCallRecord`, and stored report/result data. The evaluation CLI dispatches each non-simulated kind to an adapter keyed by a supplied persisted record map; specialized safety adapters likewise read task/attempt/event/tool/model records. A missing settled model charge produces `cost=None` and `cost_status=unknown`; it is not converted to zero. The CLI still contains an explicit `--simulate-unavailable` path, but its Observation source is `simulated`, so it is not real-task evidence.
- **Development inventory result.** Without reading or changing any heldout content, the development-named fixture files contain 40 case rows and 28 distinct `case_id` values. Four knowledge case IDs occur in four historical fixture versions each; the remaining records are distinct development or deterministic-safety candidates. Therefore file count (28) and raw distinct count (28) do **not** establish the required active set of exactly 23 frozen development cases. No active selection manifest that identifies the chosen 23, their hashes, and their relationship to the 7 heldout cases was found by filename search; `backend/tests/fixtures/evaluation/business_gold_v1.json` was deliberately not read because it may expose heldout content and no holdout-access purpose was authorized in this audit.
- **Verification.** `docker compose --profile evaluation run --rm --no-deps --user root --volume "${PWD}\\backend:/app" evaluation python -m pytest tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_run_business_evaluation.py -q` exited `0` with `90 passed in 1.73s`. Focused Ruff over the Observation schemas/adapter, evaluation CLI, and these tests exited `0`.
- **Scope and proof limit.** This confirms source-level persisted-record behavior and flags the selection/freeze gap. It does not prove that every Observation field is populated by every live Worker path, that historical cleaned tasks can all be rebuilt without their saved Observation artifacts, that `business_gold_v1.json` has the required split or immutability controls, that any heldout case passes, or that P0-2/P0 is complete. No Gold, heldout fixture, `output/`, resume, or historical evaluation artifact was modified.

### Automatic audit decision

- **Adopt:** the current persisted-Observation mechanics and their focused regression evidence. **Reject as unproven:** the required 23-development/7-heldout frozen Gold claim. **Next required decision:** authorize a narrowly scoped heldout manifest audit (metadata, split counts, and hashes only; no case text) or provide the approved 23-case selection manifest. Do not infer the selection from historical development files.

## 2026-10-16 — P0-2 Gold-inventory correction and candidate snapshot freeze (passed; P0 remains unapproved)

- **Correction to the preceding inventory note.** The earlier development-directory count was not the active Gold set. `backend/tests/fixtures/evaluation/business_gold_v1.json` is the active candidate fixture: schema validation and the existing mechanical test prove dataset version `business-gold-v1`, 30 unique cases, 23 development cases, 7 heldout cases, the required seven primary-dimension totals (4/5/5/4/4/3/5), and exactly one heldout case per primary dimension. This audit exposed only fixture metadata/counts and did not print, tune against, or modify heldout case text.
- **Freeze boundary.** The fixture SHA-256 is `a110e7c31239d7883df42608bc829ea6248902d852c544cb4ebe0bda0048cc72`. Added a regression that pins this exact candidate snapshot. It was red first with a deliberate all-zero hash (`1 failed`), then green with the actual hash. This prevents a fixture-content change from silently passing the split/coverage test; a deliberate Gold version and hash update is now required.
- **Verification.** `docker compose --profile evaluation run --rm --no-deps --user root --volume "${PWD}\\backend:/app" evaluation python -m pytest tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_observation.py tests/modules/evaluation/test_run_business_evaluation.py -q` exited `0` with `91 passed in 1.76s`. Focused Ruff on `test_business_evaluation.py` exited `0`; scoped `git diff --check` found no diff error (only the existing CRLF warning).
- **Scope and proof limit.** `business_gold_v1.json` is untracked in the current dirty worktree, so this is a hash-pinned **candidate** freeze, not a committed/reproducible baseline. It does not provide task mappings for 30 current executions, repeat runs, real-provider cost/latency, a holdout evaluation result, leak-proof access control beyond the test contract, or P0/P0-2 completion. No fixture content, Gold expectation, heldout text, `output/`, resume, or historical evaluation artifact changed.

### Automatic audit decision

- **Adopt for the candidate:** the 23-development/7-heldout fixture structure and its content-hash guard. **Continue:** create/verify real persisted task mappings and baseline measurements before any P0-2 or P0 approval; do not use the heldout cases for tuning.

## 2026-10-16 — P0-0 candidate snapshot r14 static-preflight correction (partial; P0 remains unapproved)

- **Scope repair.** The first r12 snapshot was retained as an inadmissible operator artifact because its executable filter included all `scripts/ops/` files, which mixed future-stage operations into a P0 candidate. The filter now excludes `docs/`, `output/` by omission, and `backend/.evaluation-runs/`; it admits backend code/tests/migrations, only the three named P0 preflight scripts (`collect-baseline-audit.ps1`, `inspect-queue.ps1`, `verify-stack.ps1`), and the listed root configuration files. Documentation remains indexed only through this append-only ledger.
- **Preflight root cause and narrow repair.** `docker compose images` failed in r13 because Compose also saw an exited historical `agent-worker-test-1` container whose image ID `sha256:5f71…a894a` no longer exists. That container is not a declared current service. The script now obtains `docker compose config --services` and passes only that declared list to `docker compose images`; it neither deletes nor restarts any container.
- **r14 static artifact.** `artifacts/p0/candidate-p0-0-snapshot-20261016-r14/` is a no-model, no-task snapshot from base `a0d8578a94fc0d0c7759b018c23a5d530f83a391`. It contains 134 tracked and 98 untracked candidate paths (232 total), with 0 `docs/`, 0 `output/`, 0 `backend/.evaluation-runs/`, and 0 non-P0 `scripts/ops/` paths; the hash-pinned candidate Gold fixture is included once. Its candidate patch SHA-256 is `21500d65ddb99fbab5552e0ab60b1d7c84984927af41ab4f0b9b744a1a34fc47`; untracked archive SHA-256 is `d8221df92289b3ffd06d562fd821b16ad86f167f808e038ee1fedae27a40e286`; full source-manifest tracked-diff hash is `2516c49d2fa0af75bd9e9c729269d6e40b5136bd0db159a2c926c2dc1c74a560`.
- **Verification.** PowerShell parser passed; the r14 script exited `0`; `docker compose config --quiet`, declared-service image inventory, Alembic `x1a2b3c4d5e6 (head)`, and `pytest --collect-only -q` all exited `0`. `git diff --check -- scripts/ops/collect-baseline-audit.ps1` found no diff error (only the existing Windows line-ending warning). No provider, API task, Worker task, database fixture, Gold content, holdout content, `output/`, resume, or historical evaluation artifact was changed.
- **Scope and proof limit.** This is a static candidate fingerprint and service-image resolvability check only. It does not compare a source fingerprint with files inside the running API/Worker images, does not prove the 232 candidate paths are all P0-specific rather than unclassified dirty backend work, and does not prove DB migration-current status, Worker/Redis readiness, API-to-Outbox-to-Worker behavior, real model cost/latency, repeatability, holdout performance, or P0 completion.

### Automatic audit decision

- **Adopt for the candidate:** the corrected static snapshot scope and declared-service image inventory. **Reject as P0 admission:** until the candidate is classified to P0 scope and a workspace-to-running-image fingerprint comparison is implemented and passes. Do not start a new real baseline model run on this evidence.

## 2026-10-16 — P0-0 running API/Worker source-fingerprint gate (failed as expected; P0 remains unapproved)

- **Runtime boundary confirmed.** Inspection of the active API and Worker containers shows that neither mounts the workspace source: each uses only its image `/app` content, with host mounts limited to logs and storage. Their shared `app/main.py` hash alone was equal to the workspace and therefore could not establish whole-candidate equivalence.
- **Narrow gate implementation.** `scripts/ops/collect-baseline-audit.ps1` now derives a canonical SHA-256 manifest from the frozen candidate's runtime-relevant paths (`backend/app` plus runtime dependency/config files) and streams it into both running containers for `/app` file-hash comparison. The snapshot stores each service's matched/mismatched/missing counts, mismatch paths, and manifest hashes. `-RequireRuntimeSourceMatch` is valid only with `-FreezeP0CandidateSnapshot`; it retains all audit artifacts, then exits nonzero unless both API and Worker match every selected path.
- **Observed r15/r16 result.** In r15/r16 the candidate runtime workspace manifest SHA-256 is `126d520d61197a3e70ff7b2392ff7190ef41440217f1b450bc12e5483130f640`, covering 97 selected paths. API and Worker each match 90, mismatch 7, and have 0 missing paths; their container manifests are equal (`9abdbd930b506e965377797150072fcb2eaffed53713d413efc6de3ce77d4ef2`). The shared stale paths are `analysis/sql_executor.py`, `analysis/sql_tool.py`, `evaluation/business_schemas.py`, `evaluation/business.py`, `evaluation/observation.py`, `runtime/tool_runtime.py`, and `workflow/execution.py` below `/app/app/modules/`.
- **Mechanical rejection verified.** `artifacts/p0/candidate-p0-0-snapshot-20261016-r16/` exists and records successful static collection (`docker compose config`, declared-service image inventory, Alembic head, and pytest collection all exit `0`), but the enforced invocation with `-RequireRuntimeSourceMatch` ends exit `1` with `Runtime source fingerprint does not match both running API and Worker containers.` PowerShell parser and scoped `git diff --check` pass. No provider, model call, API task, Worker task, fixture, Gold/holdout content, container restart, image rebuild, or historical evaluation artifact was changed.
- **Scope and proof limit.** This compares candidate runtime application/dependency/config source, not every Docker build-context file or runtime behavior. It proves the currently running API and Worker images are both stale relative to seven candidate runtime files; it does not identify an approved rebuild/restart window, classify all 232 candidate paths by P0 owner/intent, prove task/queue safety during a restart, or supply any real baseline/holdout result.

### Automatic audit decision

- **Adopt:** the reproducible source-alignment rejection gate. **Reject:** any new real P0 baseline run while its status is `failed`. The next technical action is a controlled image rebuild/recreate only after queue/task safety is checked and its operational impact is authorized; no silent restart is permitted.

## 2026-10-16 — P0-0 candidate image alignment and controlled API/Worker recreation (passed; P0 remains unapproved)

- **Pre-recreate safety check.** The authoritative queue audit reported `celery=0`, `reports=0`, no active/reserved/scheduled Celery tasks, and zero durable inflight analysis tasks. The sole `worker_claimed` Outbox row is task `114`: its task state is `awaiting_review`, stage `awaiting_review`, and no active execution ID, so it is not an execution requiring Worker recovery. Database and both old images reported Alembic `x1a2b3c4d5e6 (head)`.
- **Candidate-image build and offline verification.** `docker compose build api worker` completed successfully without changing a running container. The resulting API image ID is `sha256:43422833f28987491c5499a58c9644a020ef3101367722729647c055947312e8`; Worker is `sha256:bc56eb8c7ea77302828eba208dc4b4ce2b759e60da19f416a9f1b52a2719feb5`. Each was checked in a temporary `--network none --read-only --rm` container against the 97-path r16 runtime manifest; both matched 97/97, with zero missing or mismatched paths. A first check command passed `python` twice and exited before reading files; it was immediately corrected and is retained only as an operator-command failure, not image evidence.
- **Controlled recreation and recovery.** `docker compose up -d --no-deps api worker` recreated only API and Worker; it did not run `down`, alter volumes, restart Report Worker, modify the review task, or run a model/task fixture. After startup, `verify-stack.ps1` passed (PostgreSQL, Redis, object storage, API readiness, Alembic, capacity admission, and both Worker pings). Beat briefly queued periodic Outbox publish/recovery checks; Worker logs show each completed with result `0`, and the subsequent queue audit returned both queues to `0` with no active/reserved/scheduled or durable inflight task.
- **Admissible r17 fingerprint.** `artifacts/p0/candidate-p0-0-snapshot-20261016-r17/` ran with `-RequireRuntimeSourceMatch` and exited `0`. Its workspace runtime manifest SHA-256 is `126d520d61197a3e70ff7b2392ff7190ef41440217f1b450bc12e5483130f640`; API and Worker each match 97/97 with 0 mismatches. Compose config, declared-service image inventory, Alembic heads, and pytest collection also exit `0`; r17 candidate patch SHA-256 is `49bc2c446e6ae47ec288492661bce25125517e22f62a1367c98732a573ddbc68`. PowerShell parser and scoped `git diff --check` pass (the latter reports only the existing CRLF warning).
- **Scope and proof limit.** This proves the selected candidate runtime application/dependency/config files equal the new running API and Worker images, and the stack recovered its idle control-plane state. It does not classify every one of the 232 candidate paths by P0 owner/intent, prove all Docker build-context files, execute an API-to-Outbox-to-Worker business task, measure provider cost/latency, run development/holdout Gold, or approve P0.

### Automatic audit decision

- **Adopt:** r17 as the current static/runtime alignment precondition for P0 evaluation. **Continue:** freeze an explicit measurement threshold contract and select only authorized development cases before any provider-backed baseline run; holdout remains unread for tuning and P0 remains unapproved.

## 2026-10-16 — P0-3 versioned threshold-contract enforcement (mechanism passed; actual P0 contract not yet frozen)

- **Gap confirmed.** `run_business_evaluation.py` already records hard-gate status, P95 duration, settled cost, and unknown cost status, but had no versioned threshold input or mechanical refusal of a drifting fixture/run. Existing one-case artifacts are not comparable baselines: they differ in fixture, have unavailable Git revision, or both. No historical result was used to infer a new threshold.
- **Narrow implementation.** Added `app.modules.evaluation.thresholds.EvaluationThresholdContract` and optional CLI `--threshold-contract`. A contract pins the fixture SHA-256, required split, expected case count, total settled-cost ceiling, optional P95 ceiling, and whether persisted-task Observation, hard-gate pass, and settled cost are mandatory. The CLI records the contract path/hash/violations in `run.json`; it writes both run artifacts first, then exits nonzero on any violation. Thus a failed measurement remains inspectable but cannot be promoted as a pass.
- **Regression evidence.** The focused evaluation suite passed `16` tests. One CLI replay proves a cost-cap violation is retained in its output then raises `SystemExit`; the pure-contract regression proves matching input passes and fixture-hash drift plus `cost_status=unknown` produce exactly `fixture_sha256` and `settled_cost` violations. Focused Ruff passed for the new module, CLI, and tests; scoped `git diff --check` found no diff error (only the existing CRLF warning).
- **Scope and proof limit.** This adds enforcement mechanics only. No actual P0 threshold JSON has been created, no Gold/holdout content was changed or read for tuning, no model/API/Worker task ran, and no quality/P95/candidate-deterioration value was invented. The user-authorized `$0.30` ceiling is a task-cost authorization; it is not silently promoted to a quality or latency acceptance threshold.

### Automatic audit decision

- **Adopt:** the reusable threshold loader and refusal behavior. **Continue, but do not run a provider baseline yet:** freeze the actual P0 development contract with an explicit P95 limit and permitted candidate-versus-baseline deterioration rule, then hash it in this ledger before selecting a development case. P0 remains unapproved.

## 2026-10-16 — P0-3 frozen-baseline relative-comparison guard (mechanism passed; no P0 baseline run)

- **Gap repair.** The previous contract enforced only absolute settled cost and optional P95, so it could not enforce the plan's same-model/same-data candidate rule. A relative limit without a locked baseline artifact would be tunable after the candidate, so it is not admissible evidence.
- **Narrow implementation.** A comparison-enabled contract now requires all three values together: the SHA-256 of a baseline `run.json`, a P95 multiplier, and a settled-cost-per-trusted-success multiplier. `--baseline-run` parses that artifact and rejects a non-baseline label, a different dataset version, a different model version, or a different ordered case selection. The evaluator records the supplied baseline path/hash, reports a hash mismatch, unavailable metrics, P95 regression, and cost-per-trusted-success regression as deterministic violations, writes the candidate artifact, then exits nonzero.
- **Regression evidence.** `docker compose --profile evaluation run --rm --no-deps --user root --volume "${PWD}\\backend:/app" evaluation python -m pytest tests/modules/evaluation/test_run_business_evaluation.py tests/modules/evaluation/test_thresholds.py -q` exited `0` with `17 passed in 1.17s`. Focused Ruff over the threshold module, CLI, and both tests exited `0`; scoped `git diff --check` found no diff error (only the existing CRLF warning). The direct CLI regression supplies a hash-locked comparable baseline, writes that hash into the rejected candidate artifact, and records both absolute-cost and normalized-cost failure. The pure contract regression covers P95 and normalized-cost breaches at a frozen `1.20` multiplier.
- **Scope and proof limit.** `1.20` appears only in an isolated regression fixture to prove the arithmetic; it is not an actual P0 contract choice. No production or development baseline artifact was selected, no actual P0 threshold JSON exists, no provider/API/Worker task ran, and no Gold or heldout content was changed or read for tuning. The current API/Worker images predate this new `app/modules/evaluation/thresholds.py` source, so r17 cannot be reused as evidence that they match the latest workspace.

### Automatic audit decision

- **Adopt:** the mechanical, hash-bound baseline comparison guard. **Continue:** before provider work, freeze a concrete development contract (including the user-authorized absolute cost cap and the chosen P95/cost multipliers), rebuild/recreate API and Worker only after a fresh idle-queue preflight, then collect a new baseline. P0 remains unapproved.

## 2026-10-16 — P0-0 r18 latest runtime alignment after threshold-guard update (passed; P0 remains unapproved)

- **Idle-window preflight.** Before image work, `inspect-queue.ps1` reported both broker queues at `0`, both Workers active/reserved/scheduled sets empty, and `analysis_tasks_inflight_total=0`. Task `114` was independently checked as `awaiting_review` with no `active_execution_id`; its retained `worker_claimed` Outbox event is not an active execution.
- **Controlled rebuild/recreate.** `docker compose build api worker` completed, followed by `docker compose up -d --no-deps api worker`. Only API and Worker were recreated; no database, volume, Report Worker, review task, fixture, or provider task was changed. `verify-stack.ps1` then passed PostgreSQL, Redis, object storage, Alembic head, API readiness, capacity admission, and both Worker pings.
- **Admissible r18 fingerprint.** `artifacts/p0/candidate-p0-0-snapshot-20261016-r18/` ran with `-FreezeP0CandidateSnapshot -RequireRuntimeSourceMatch` and exited `0`. Its latest candidate runtime manifest is `d15a9e205ac491b4fc07e7608331aa316e3c48079ce7e974efc2aea762b5e3b8`, with 98 selected paths. API and Worker each match `98/98`, with zero mismatches. Compose config, Alembic heads, and pytest collection each exit `0`; candidate patch SHA-256 is `81fd8c03dda9803c524a8f6ce85882d4500f4aaeaa5911ec39a176e6c46e6799`. The post-recreate queue audit again shows both queues idle and no in-flight execution.
- **Scope and proof limit.** This supersedes r17 only as a candidate runtime-source alignment/control-plane precondition. It does not classify all candidate paths by P0 owner/intent, prove a real API-to-Outbox-to-Worker business execution, create/freeze a real P0 threshold contract, call a Provider, measure cost/P95, run a development or heldout Gold case, or approve P0.

### Automatic audit decision

- **Adopt:** r18 as the current runtime-alignment precondition for a later P0 measurement. **Continue:** actual P0 P95/budget/multiplier values must be frozen before a provider baseline; P0 remains unapproved.

## 2026-10-16 — P0-3 real-Provider capability preflight (configuration passed; no Provider call)

- **Current configured capability.** In both the running API and Worker, `get_model_gateway()` resolves to `DeepSeekGateway` with provider `deepseek` and model `deepseek-v4-flash`; it is not `LocalModelGateway`. The DeepSeek credential is configured in both containers. Secret values were not printed or read into this ledger.
- **Budget boundary.** The running code's `analysis_task_model_max_cost` is `$0.15` per task, which is stricter than the user-authorized `$0.30` cap. This configuration limit is not silently treated as an evaluation-run budget or a candidate acceptance threshold; a formal P0 contract must state its own applicable cap.
- **Scope and proof limit.** Gateway construction did not make an HTTP/Provider request. This proves configuration selection and credential presence only; it does not prove provider reachability, valid account/quota, actual model response, charge settlement, P95, quality, API-to-Worker execution, or P0 approval.

### Automatic audit decision

- **Adopt:** `DeepSeekGateway` is available for a future, cost-capped real P0 single-case measurement. **Continue:** freeze the measurement's absolute P95, applicable run cost ceiling, and `1.20`-or-other relative rule before submitting it; P0 remains unapproved.

## 2026-10-16 — P0-0 explicit candidate-path-manifest admission guard (mechanism passed; r18 not reclassified)

- **Root gap corrected.** The prior collector allowed every changed `backend/**` path, so its selected 232-path snapshot could not prove that all paths were P0 work. Path location is not owner/intent classification. The collector now requires `-P0CandidatePathManifest` for every frozen candidate snapshot.
- **Admission contract.** The manifest is JSON with `schema_version: "p0-candidate-paths-v1"` and a non-empty, unique `paths` list. Every listed path must be a current tracked/untracked change and satisfy the existing executable-scope exclusions; the manifest SHA-256 and exact selected paths are stored in the snapshot. Empty runtime selections now fail the runtime fingerprint instead of passing vacuously.
- **Verification.** PowerShell parser validation passed. A fresh subprocess invocation with `-FreezeP0CandidateSnapshot` but no path manifest exited nonzero with the required diagnostic `-P0CandidatePathManifest is required with -FreezeP0CandidateSnapshot.` Scoped `git diff --check` found no diff error (only the existing CRLF warning). No new candidate snapshot, Provider call, API/Worker task, database/fixture/Gold/holdout change, or container action occurred.
- **Scope and proof limit.** The guard prevents a future unclassified freeze but does not classify the current dirty worktree, infer its owner/intent, or retroactively make r18 an admissible P0-only snapshot. It does not prove any business path or P0 completion.

### Automatic audit decision

- **Reject as P0 admission:** r18's broad selected-path list remains unclassified. **Continue:** provide an explicit P0 path manifest based on the owner/intent decision, then create a new runtime-aligned snapshot before any provider measurement; P0 remains unapproved.

## 2026-10-17 — P0 development single-case candidate r6 (quality hard gate passed; comparison contract rejected; P0 remains unapproved)

- **Frozen input and candidate boundary.** The development-only fixture is `business-hybrid-revenue-causality-development-v1`, SHA-256 `c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c`; no heldout case was read, changed, or submitted. The synthetic corpus manifest SHA-256 is `1307b4f130b70bda39a16f6e2f5e60ba24c18eb8b9fa515ea8254f265d841148`. Candidate snapshot `artifacts/p0/candidate-p0-0-snapshot-20261017-r25/` selected the explicit 103-path P0 manifest, SHA-256 `388880cbfd45c32b61c62b1a986a0a5c52999b73fb72687c15e114d2dd8a0c3d`; its 79 runtime paths matched both API and Worker images with zero mismatch, and pytest collection exited `0`.
- **Thresholds frozen before r6.** The candidate contract records a per-case settled-cost ceiling of `$0.15`, absolute P95 ceiling `600000 ms`, and frozen baseline comparison multipliers of `1.20` for P95 and unit trusted-success cost. The comparison baseline artifact remains SHA-256 `454368de454f09f8f055714baf258347c393b5fadc321c9b6acd931b502aec7f`; it has zero trusted successes, which is retained rather than repaired after observing the candidate.
- **Bad-case repair and regression.** r5 revealed that model-generated SQL `purpose` text was still copied into publishable `DataEvidence` even though confirmed facts used a safe label. `build_data_evidence` now applies the existing deterministic `render_evidence_purpose` boundary, so published report evidence is labelled only `已授权经营数据`; the raw SQL-generation result remains audit metadata. The targeted 130-test regression command exited `0`; focused Ruff and scoped `git diff --check` exited `0` (the latter only reported existing CRLF warnings). r5 was not approved or published and its isolated resources were cleaned up.
- **Real Provider result.** r6 submitted exactly one development case through API → Outbox → Worker with DeepSeek `deepseek-v4-flash`. The reviewer was approved only after inspecting the persisted SQL, returned value, report evidence label, citation scope, deterministic validation, and causal limitation; publication then completed. Persisted evaluation reports SQL-result equivalence, numeric consistency, citation scope, confirmed fact, supported claim, forbidden-claim freedom, deterministic validation, and security hard gates all passed. The one task used 6 model calls, 10,854 tokens, settled cost `$0.004233`, and published duration `104452 ms`; its P95 is below the absolute ceiling and below the frozen baseline P95 multiplier limit of `104493.6 ms`.
- **Mechanical rejection retained.** `scripts.run_business_evaluation` wrote `backend/.evaluation-runs/p0-development-single-candidate-20261017-r6/evaluation-terminal/run.json` and then exited `1` with the sole violation `cost_per_trusted_success_multiplier`. The candidate's hard gate itself is `passed` with one trusted success, but the baseline has zero trusted successes, so no normalized-cost denominator exists. This is correctly non-passing under the pre-registered comparison contract; it must not be relabelled as a cost pass or replaced after the fact. r6 cleanup completed and removed task 136 plus its isolated fixture resources while preserving the run artifacts.
- **Scope and proof limit.** This is one real Provider run on a synthetic development case, not a repeatability study, holdout result, full non-E2E suite, real-business validation, or P0 approval. The unresolved normalized-cost baseline prevents candidate adoption under the frozen contract. P0 remains unapproved.

### Automatic audit decision

- **Reject as threshold-admissible candidate:** r6 until a separately planned, pre-registered comparable baseline has at least one trusted success. **Adopt only for diagnosis:** the report-evidence purpose boundary and r6's single-case hard-gate evidence. **Continue:** do not change the current Gold, threshold, or baseline artifact; decide the next independent baseline/measurement slice before more Provider calls.

## 2026-10-17 — P0 E2 non-E2E test baseline r27 (classified, not clean; P0 remains unapproved)

- **Frozen candidate and execution boundary.** `artifacts/p0/candidate-p0-0-test-baseline-20261017-r27/` used the explicit 103-path P0 manifest (SHA-256 `388880cbfd45c32b61c62b1a986a0a5c52999b73fb72687c15e114d2dd8a0c3d`). Its selected runtime source manifest covered 79 paths; API and Worker each had zero mismatches. The script set `APP_ENV=test` and `DATABASE_NAME=agent_platform_test`, ran collection, `ruff check app tests`, and `pytest tests -q -rs -m 'not e2e and not slow'`. No Provider, development/holdout business case, production database, or fixture content was changed.
- **Result and delta.** Collection exited `0`. The first r26 baseline recorded `797 passed, 2 failed, 4 skipped, 7 deselected`; one failure was an attachment-upload test that assumed object storage was absent while the test process loaded complete local object-storage configuration from `backend/.env`. The test now explicitly injects the existing `DirectUploadStorageUnavailableError` at the storage-factory boundary. Its isolated regression passed, and r27 improved to `798 passed, 1 failed, 4 skipped, 7 deselected` in `34.47s`.
- **Remaining pytest classification.** The sole failure is `tests/integration/identity/test_auth.py::test_bootstrap_owner_only_works_before_any_company`. Its test setup tries to delete every company to construct the "first company" precondition, but in the full-suite order a document retained by another test connection references a company through `documents.company_id` with `RESTRICT`; the bulk delete raises `ForeignKeyViolation` before exercising the bootstrap endpoint. The failure is therefore shared-test-database/order coupling, not evidence that bootstrap authorization behavior passed or failed. A rejected diagnostic attempt to use `TRUNCATE ... CASCADE` established that the application test role has no truncate privilege; it was reverted. Fixing this requires a separately scoped test-isolation design, not a broad destructive cleanup of dependency tables.
- **Skip and deselection classification.** Two LocalStack upload proofs are intentionally skipped because `RUN_LOCAL_OBJECT_STORAGE_E2E=1` is not set. Two SQL-executor tests are intentionally skipped because the local non-E2E process has no Docker business database. Seven cases are intentionally deselected by the declared `not e2e and not slow` baseline selector. These are not counted as pass.
- **Static classification.** Ruff exited `1` with 326 findings: `I001=128`, `B008=116`, `ISC004=19`, `TRY004=12`, `F401=10`, `BLE001=8`, `RUF100=8`, `SIM117=5`, `UP035=3`, `RUF012=3`, and 14 findings across smaller existing rule groups. Ruff reports 155 mechanically fixable findings, of which 24 require unsafe fixes. No bulk formatter or unrelated source edit was applied, so this remains a failing static baseline rather than a false green result.
- **Scope and decision.** r27 is the requested full non-E2E baseline record and classifies every current failure/skip/deselection, but it is not a clean suite and does not prove E2's clean-test condition, full E2E, object-storage E2E, business database integration, or P0 completion.

### Automatic audit decision

- **Adopt for measurement:** r27 as the current reproducible non-E2E baseline and the explicit upload-unavailability test isolation. **Continue:** plan one bounded test-isolation slice for the bootstrap precondition, and separately decide whether the 326 Ruff findings are an in-scope quality debt slice; do not call this baseline passing or promote P0.

## 2026-10-17 — P0 E2 bootstrap-test isolation r28 (pytest baseline clean; static debt remains; P0 remains unapproved)

- **Root cause and rejected approach.** r27's sole pytest failure did not reach bootstrap logic: the test attempted to delete every shared-test-database company to create a zero-company precondition, but full-suite data could include `documents` with a `RESTRICT` foreign key. A diagnostic `TRUNCATE ... CASCADE` was rejected because the application test role lacks truncate permission, and it was reverted. Foreign-key inspection found several other `RESTRICT` children of `companies`; deleting tables one at a time would be an unsafe, order-dependent test cleanup strategy.
- **Narrow isolation repair.** `tests/integration/identity/test_auth.py` now creates only the three actual bootstrap tables (`users`, `companies`, `company_members`) on a per-test SQLite memory engine using `StaticPool`, and overrides the FastAPI database dependency with a fresh Session per request. The test still invokes the real `/auth/bootstrap-owner` endpoint and `bootstrap_first_company_owner` service; it asserts owner membership after the first request and `409` after the second. It does not claim PostgreSQL constraints, RLS, migrations, or application-wide database behavior. `tests/modules/input_artifacts/test_api.py` retains the preceding explicit unavailable-storage factory injection, so its 503/no-session assertion is independent of developer `.env` object-storage configuration.
- **Verification.** Focused pytest over both repaired cases exited `0` with `2 passed`; focused Ruff for the identity test and scoped `git diff --check` exited `0` (only the pre-existing Windows CRLF warning appeared). Candidate snapshot `artifacts/p0/candidate-p0-0-test-baseline-20261017-r28/` again selected the 103-path manifest and had API/Worker runtime fingerprints match all 79 paths with zero mismatch. It recorded collection exit `0`, pytest exit `0` with `799 passed, 4 skipped, 7 deselected in 35.69s`.
- **Static and skipped boundaries.** Full Ruff remains nonzero: 325 findings, 154 mechanically fixable and 24 unsafe fixes. The four skips remain two opt-in LocalStack proofs and two business-database SQL executor proofs; the seven deselections remain the declared `not e2e and not slow` selector. None are counted as pass, and no bulk formatter or external E2E was run.
- **Scope and decision.** This closes the observed full-suite pytest ordering failure and provides a clean non-E2E pytest baseline. It does not close static lint debt, E2E/slow coverage, LocalStack/object-storage proof, business database integration, holdout evaluation, or P0.

### Automatic audit decision

- **Adopt for E2 pytest measurement:** r28's reproducible `799 passed` non-E2E baseline and self-contained bootstrap precondition test. **Continue:** keep Ruff as a separately classified static failure, then select the next P0 measurement/A3 trace slice without treating r28 as P0 approval.

## 2026-10-17 — P0 A3 persisted task trace verification (existing capability; P0 remains unapproved)

- **Actual trace chain.** The existing `scripts/render_task_trace.py` command is tenant-scoped by both `company_id` and `task_id`. It loads the persisted `AnalysisTask`, `TaskExecutionAttempt`, `WorkflowEvent`, `ModelCallRecord`, and `ToolCallRecord`, then renders a time-sorted static HTML page. It includes only audit metadata: task/attempt state, workflow node/event, provider/model or tool, result status/error code, duration, tokens, and cost. It deliberately omits the task text, prompts, SQL, tool arguments/results, report body, and event details; requested-company mismatch raises an error instead of exposing another tenant's task.
- **Retained real-run replay.** No task or provider was run. The already-preserved, cleaned-up development artifacts were inspected read-only. r5 trace `backend/.evaluation-runs/p0-development-single-candidate-20261017-r5/traces/task-135.html` shows one completed execution attempt whose terminal workflow state is `awaiting_review`; it is a controlled non-publication state, not a claimed successful publication or a provider error. r6 trace `backend/.evaluation-runs/p0-development-single-candidate-20261017-r6/traces/task-136.html` shows two persisted attempts: attempt 1 ends at `awaiting_review`, attempt 2 records a separate claim and reaches `completed`. Both traces contain workflow/model/tool rows with per-call duration, tokens, and settled-cost metadata. The earlier r4 failure trace remains the separately recorded real error-classification evidence; it was not re-run or modified here.
- **Verification.** From `backend/`, `..\\.venv-py313\\Scripts\\python.exe -m pytest tests/scripts/test_render_task_trace.py -q` exited `0` with `2 passed in 0.23s`; `..\\.venv-py313\\Scripts\\python.exe -m ruff check scripts/render_task_trace.py tests/scripts/test_render_task_trace.py --ignore EXE002,BLE001` exited `0`. `render_task_trace.py --help` also exited `0`, confirming its required `--company-id`, `--task-id`, and `--output` interface. No source, test, fixture, Gold/heldout, historical evaluation artifact, `output/`, or runtime state was modified by this verification.
- **Scope and proof limit.** This proves the trace renderer's narrow privacy and tenant-boundary regressions plus two retained synthetic development task histories. It does not prove every Worker failure is classified, trace retention/authorization policy in production, an API-to-Outbox-to-Worker run made from the present dirty workspace, historical artifact integrity beyond the inspected files, heldout behavior, or P0 completion. Full-suite Ruff remains a separately recorded failing static baseline.

### Automatic audit decision

- **Adopt for A3 evidence:** the existing privacy-safe, persisted-record trace path and its focused regression evidence. **Continue:** retain the r4 real-error trace as the failure-classification example; do not call r5's `awaiting_review` state a failure or r6's cleaned-up task a live end-to-end proof. P0 remains unapproved.

## 2026-10-17 — P0-0 candidate-path closure and Unicode-safe snapshot r33 (passed; P0 remains unapproved)

- **Call-closure correction.** The P0 preparation harness imports `scripts.render_task_trace`, but the frozen 103-path manifest omitted both `backend/scripts/render_task_trace.py` and its tenant/privacy regression `backend/tests/scripts/test_render_task_trace.py`. The manifest now contains 105 current P0-classified paths; this is a scope correction only and does not add a runtime feature.
- **Snapshot root-cause repair.** r29/r30 were incomplete observation artifacts and are not evidence. r31 used Windows PowerShell rather than the current PowerShell runtime and failed before collection because that host lacked `Get-FileHash`. r32 then exposed the product-script defect: `collect-baseline-audit.ps1` attempted `git hash-object` for every untracked file, including excluded user `output/pdf` paths, where a non-ASCII filename made Git fail and produced a subsequent null-value error. The collector now records every excluded untracked path with `content_hash_status=excluded_non_p0` and a null blob hash; only P0-executable untracked paths are blob-hashed. This preserves the exclusion boundary and prevents excluded user artifacts from blocking a P0 candidate snapshot.
- **Verification.** JSON validation, `pytest tests/scripts/test_prepare_business_evaluation.py tests/scripts/test_render_task_trace.py -q`, and focused Ruff all exited `0` (`16 passed`). PowerShell parse and scoped `git diff --check` passed (only the existing CRLF warning). The corrected r33 invocation used `-FreezeP0CandidateSnapshot`, the explicit P0 manifest, and `-RequireRuntimeSourceMatch`; it completed with collection exit `0`, 105 candidate paths (manifest SHA-256 `8229b98c6dcab41e16c9519caedd16d8ca47a05ce73c09615115c96c91e4a48e`), 79 runtime paths, and zero API/Worker mismatches. It intentionally did not run full Ruff or the non-E2E suite, so their status is not changed by r33. Its source manifest records 103 hashed P0-executable untracked paths and 522 excluded untracked paths with zero excluded-path hashes.
- **Scope and proof limit.** No Provider, API task, Worker task, model call, review/publication, Gold/heldout fixture, historical evaluation artifact, `output/` file, resume, container, or database state was changed. r33 proves only current P0 path classification, safe static collection, and runtime-source alignment. It does not prove business correctness, cost/P95 repeatability, a comparable baseline, full static cleanliness, E2E behavior, or P0 completion.

### Automatic audit decision

- **Adopt for P0-0:** r33 as the current candidate-scope and runtime-alignment precondition. **Continue:** P0-3 still requires a separately planned reproducibility/baseline measurement; r6 remains a rejected comparison candidate because its predecessor baseline has zero trusted successes.

## 2026-10-17 — P0-3 independent trusted-success baseline r3 (passed as a future baseline; P0 remains unapproved)

- **Preflight and environment boundary.** Immediately before submission, `verify-stack.ps1` passed and the queue audit reported zero broker depth, no active/reserved/scheduled Worker tasks, and zero in-flight analysis tasks; the server-owned per-task model budget was `$0.15`. A first host-local preparation failed before task submission because `ACME_DEMO_DATABASE_PASSWORD` is intentionally injected into API/Worker containers but absent from the host process. Its isolated prepare manifest had zero task mappings and was cleaned successfully. No credential was printed, copied into `.env`, or persisted.
- **One disposable development execution.** The same frozen development fixture and one frozen corpus document were copied only to API-container `/tmp`; the API-container harness created and submitted task `137` under the server-owned `$0.15` cap. It reached `awaiting_review` with eight settled model calls and settled cost `$0.004263`. The independent review checked the completed draft's schema, current-tenant frozen citation scope, one data-backed fact, one cited hypothesis, one document finding, expected numeric evidence, causal-boundary qualification, and safe deterministic data-evidence label. A first host-side direct service invocation rolled back before any state change because that standalone process had not registered all ORM mappings; the same review service then ran in the normal API runtime, approved the pending request, and published through the normal Outbox path. Task `137` reached `completed` with a persisted report and no active execution.
- **Formal baseline result and cleanup.** `run_business_evaluation` against the persisted task wrote `backend/.evaluation-runs/p0-development-single-baseline-20261017-r3-container/evaluation-terminal/run.json`: comparison `baseline`, `1/1` trusted success, zero failures/unknowns, hard gate `passed`, P95 `76587 ms`, and settled cost `$0.004263`. The baseline run SHA-256 is `4763c12cc36b2be31a5ca47e98dc76a1171b54f1eb9ac69e11388d4f94eaed39`. Harness cleanup rendered the metadata-only trace, completed its resource cleanup, and direct lookup confirmed task `137` no longer exists; the final queue audit is idle. The retained trace has a timeline but no raw SQL or task question.
- **Future comparison contract.** Added `p0_development_single_case_r3_baseline_candidate_thresholds.json` before any future code candidate. It pins the baseline run SHA-256, the existing `$0.15` absolute run cap, `600000 ms` absolute P95 cap, and the user-authorized `1.20` P95 and unit-trusted-success-cost multipliers. A zero-cost saved-Observation self-comparison passed with no violations. This verifies threshold wiring only; it is not a second Provider run or evidence of an improvement.
- **Current fingerprint and scope.** r34 re-froze the 106-path P0 manifest (SHA-256 `32075826b62fbe2460e0051b08015f38b441ebc30a2e6be5878710a203ae75cb`), collected pytest successfully, and matched all 79 selected runtime paths in both API and Worker with zero mismatch. Full Ruff and the full non-E2E suite were intentionally not rerun by r34; their earlier classification remains unchanged. No Gold/heldout content, user `output/`, resume, historical evaluation artifact, production tenant, or runtime source code was changed by this baseline slice.

### Automatic audit decision

- **Adopt for P0-3:** r3 as the locked, reproducible future comparison baseline and the new pre-candidate `1.20` multiplier contract. **Do not retroactively adopt r6:** it remains compared to the prior zero-success baseline and therefore correctly failed its normalized-cost gate. **Continue:** any next behavioral candidate must freeze r34 plus the new contract before a new development-only comparison; P0 as a whole remains unapproved.

## 2026-10-17 — P0-2 Gold inventory and P0 evaluation aggregate-budget guard (mechanism passed; P0 remains unapproved)

- **Gold inventory, without heldout content review.** `business_gold_v1.json` remains SHA-256 `a110e7c31239d7883df42608bc829ea6248902d852c544cb4ebe0bda0048cc72`; its schema regression verifies 23 development and 7 heldout cases, unique IDs, and one heldout primary coverage tag for each of the seven categories. The present P0 work did not print, modify, select, or submit any heldout case. This confirms the frozen 23+7 contract exists; it does not create current persisted task mappings for all 23 development cases.
- **Frozen budget and comparison values.** The next development single-case submission is bounded by `$0.15` server-owned task cost, `600000 ms` P95, and a `1.20` multiplier for both P95 and unit trusted-success cost. The aggregate P0 evaluation limit is now `$0.30`; it is a P0 measurement authorization boundary, not a production SLO or a claim that `$0.30` purchases 23 complete executions.
- **Narrow guard.** Added `scripts/ops/assert-p0-evaluation-budget.ps1`. Before a paid P0 task, it receives the explicit prior `run.json` paths and the proposed next task maximum, rejects missing/unknown/unsettled costs and duplicate run paths, then rejects a projected total over `$0.30`. It does not discover historical runs or alter them, so the operator must provide every in-scope prior P0 run explicitly. This avoids silently treating unknown provider cost as zero.
- **Current preflight computation.** Supplying the retained r6 and r3 single-case artifacts produced settled cost `$0.008496` (`$0.004233 + $0.004263`); reserving the next `$0.15` task yields `$0.158496` projected and `$0.141504` remaining. r6 is included in spend even though its old comparison contract was rejected. No task, provider call, API/Worker state, Gold/heldout content, historical evaluation artifact, or user `output/` file was changed by this calculation.
- **Verification.** `pytest tests/scripts/test_assert_p0_evaluation_budget_script.py tests/scripts/test_prepare_business_evaluation.py tests/scripts/test_render_task_trace.py -q` exited `0` with `18 passed`; focused Ruff exited `0`; PowerShell parser validation passed; the actual two-artifact budget preflight above exited `0`. The new regression covers both the accepted two-artifact projection and rejection of unknown cost or projected overspend.

### Automatic audit decision

- **Adopt:** the explicit `$0.30` aggregate preflight guard, the `$0.15` next-task reservation, and the already frozen `600000 ms`/`1.20` comparison constraints. **Reject P0/P0-2 completion:** the 23-case Gold set has no current r35-or-later persisted development mapping; the successful single-case baseline does not fill that gap. **Continue:** re-freeze the P0 executable candidate after this P0 script addition, then select one independently justified development measurement or stop when the aggregate guard would reject its reserved cost.

## 2026-10-17 — P0-2 Gold data-path baseline r37 (real Provider Bad Case; P0 remains unapproved)

- **Frozen input and runtime candidate.** This selected only the development case `data-east-sales-comparison` from unchanged `business_gold_v1.json` (SHA-256 `a110e7c31239d7883df42608bc829ea6248902d852c544cb4ebe0bda0048cc72`); no heldout case was read, selected, or submitted. Its pre-registered baseline contract is `p0_gold_data_east_sales_comparison_baseline_thresholds.json`: one development persisted-task observation, `$0.15` maximum settled cost, `600000 ms` P95, hard-gate pass, and settled cost required. r37 froze the current 110-path P0 manifest (SHA-256 `7c1fc007e44e38394c364fd9eaf5035f8c3ce4e08b30c63770a693d11217a015`), recorded 79 runtime source paths, and matched both API and Worker with zero mismatches; collection exited `0`.
- **Preflight and bounded execution.** `verify-stack.ps1` passed; both queues, active/reserved/scheduled Worker lists, and durable in-flight task count were zero. API and Worker both reported the server-owned `$0.15` task cap. The aggregate guard then included r6 and r3 recorded spend (`$0.008496`) plus a planned `$0.15`, projecting `$0.158496` under the `$0.30` authorization. The API-container harness submitted exactly task `138` through API → Outbox → Worker with `DeepSeekGateway/deepseek-v4-flash`, an isolated tenant and source, and no document scope.
- **Formal result.** Task `138` terminalized `partial` after four settled provider calls and 7,358 tokens; its exact task ledger cost was `$0.0028653` and its evaluation artifact renders the six-decimal settled cost `$0.002866`. The persisted-task evaluation is `backend/.evaluation-runs/p0-gold-data-east-sales-comparison-baseline-20261017-r37/evaluation-terminal/run.json`, SHA-256 `b73e5fb1bbf7e51d6d008e9cfbfa7dc93102139678dde04bc7e1732ddc4be5f9`. It reports P95 `5679 ms`, cost status `passed`, 0 unknowns, route `data_only`, deterministic numeric validation and security checks passed, but actual outcome `insufficient_evidence`. Frozen failures are exactly `entity_scope_correct`, `sql_result_equivalent`, and `outcome_correct`; the formal threshold command wrote the artifact and exited `1` with `hard_gate_passed`. No review was attempted because the task was not `awaiting_review`.
- **Cleanup and audit trace.** After terminal artifact capture, the harness produced `traces/task-138.html`, completed cleanup, and direct platform-database checks found zero residual task, attempt, model-call, tool-call, workflow-event, user, company, data-source, or schema-snapshot rows. The trace contains its timeline but no task question or `SELECT ` text. Post-cleanup queues and durable in-flight count are zero. No production tenant, business-database write, Gold/heldout modification, user `output/` file, or resume was changed.
- **Verification and cumulative cost.** The three retained artifacts (r6, r3, r37) pass the aggregate guard with recorded settled spend `$0.011362` and `$0.288638` remaining before another planned task. Focused Gold/threshold/budget regressions passed `6`; Ruff over the evaluator, thresholds, and new budget test passed. This narrow real failure does not establish that SQL routing is generally broken, nor does a single outcome justify changing Gold, prompt, Planner, DataAgent, or report code.

### Automatic audit decision

- **Adopt for P0-2 measurement:** r37 is one current-source, real API→Outbox→Worker persisted development observation and a retained data-path Bad Case. **Reject as a successful baseline and reject P0/P0-2 completion:** its hard gate failed. **Continue:** perform a source-level failure trace of the three frozen violations before proposing one root-cause-only candidate; do not rerun this input or tune the fixture to conceal the failure.

## 2026-10-17 — P0-2 Gold fingerprint comparability correction (replay-only; P0 remains unapproved)

- **Root cause.** r37's metadata-only trace shows the Data node completed successfully, so the terminal `insufficient_evidence` did not originate from a direct SQL no-records path. Read-only comparison of the frozen Gold contract and persisted Observation found that the actual period was reversed (`2025-07 compared_to 2025-08` rather than the expected order), which explains `entity_scope_correct`; the Reviewer/terminal path still produced `partial`, which explains `outcome_correct`. The privacy-safe trace deliberately does not retain the detailed Reviewer rationale, so the exact Reviewer cause is `unknown` after cleanup.
- **Evaluator defect, not a Gold adjustment.** All 23 development Gold cases carry a scenario-shaped expected fingerprint; `result_fingerprint_from_data_result` only persists the SHA-256 `{algorithm,value}` form. For a data case, the prior raw-dict equality therefore labeled incomparable evidence as `sql_result_equivalent=failed`, even if every other observation field was made correct. The pure-memory probe confirmed the existing region suffix normalizer accepts `华东/华东区`; that text difference was not the r37 entity failure. Gold and heldout files were not modified.
- **Minimal repair.** `evaluate_case` now treats a scenario-versus-SHA-256 fingerprint-shape mismatch as `unknown`; missing actual fingerprints remain unknown, while two comparable SHA-256 fingerprints still require exact equality and a mismatch remains failed. Unknown stays in the hard gate and cannot promote a candidate. Added regressions for both shape mismatch and strict comparable-hash mismatch.
- **Verification and replay.** `pytest tests/modules/evaluation/test_business_evaluation.py tests/modules/evaluation/test_run_business_evaluation.py tests/modules/evaluation/test_thresholds.py -q` passed `76`; scoped Ruff passed. The saved r37 Observation was then replayed without a Provider, Worker, tenant, or database task. Replay artifact `backend/.evaluation-runs/p0-gold-data-east-sales-comparison-baseline-20261017-r37/evaluation-contract-replay/run.json` SHA-256 `0dacf2d5b60e1db80ee0c2ccde0aa210597ce700efc672ce96f9f53ae7d8e940` correctly reports violations only `entity_scope_correct` and `outcome_correct`, with `sql_result_equivalent` in `unknown_checks`; it still fails `hard_gate_passed` and is not a new baseline or paid result.

### Automatic audit decision

- **Adopt:** the fail-closed fingerprint comparability classification and its zero-cost replay evidence. **Reject P0/P0-2 completion and reject r37 as a successful baseline:** the real reversed-period/partial outcome remains unresolved, and the Gold SQL fingerprint contract requires a separately frozen, reviewable expected-hash strategy before it can become a passing data-equality proof. **Continue:** re-freeze the changed evaluator with API/Worker source alignment, then investigate the reversed-period/Reviewer-partial causal chain as one variable; do not change Gold, use heldout input, or resubmit r37 unchanged.

## 2026-10-17 — P0-2 r37 period-direction trace and r38 runtime-alignment failure (no Provider; P0 remains unapproved)

- The planner contract explicitly requires a model-produced `evaluation_scope.period`; `tasks._evaluation_facts` persists that string unchanged. The r37 value reversed the requested comparison order. There is no safe generic string rule that can reverse it after the fact without risking a different question's meaning, so this remains a Planner-output/validation gap rather than a candidate for ad-hoc normalization. The cleaned metadata trace does not retain detailed Reviewer rationale, so the precise reason for the resulting Reviewer `partial` remains `unknown`.
- r38 attempted the required P0 candidate snapshot after the fingerprint-classification source change. It did not create a task, call a Provider, or change database state, but correctly failed `-RequireRuntimeSourceMatch`: running API and Worker source does not contain the changed evaluator. The source-level focused tests are green, but they are not proof of live API/Worker behavior. No runtime rebuild or container stop was performed without a new explicit authorization.

### Automatic audit decision

- **Reject r38 as runtime-aligned.** **Continue only after API and Worker are explicitly authorized to be rebuilt/recreated from the current source**, followed by stack/queue preflight and a new snapshot. P0 remains unapproved.

## 2026-10-18 — P0-2 API/Worker rebuild and r39 runtime-source alignment (precondition passed; P0 remains unapproved)

- **Authorized scope.** The operator explicitly authorized rebuilding and recreating only `api` and `worker`. `docker compose build api worker` followed by `docker compose up -d --no-deps --force-recreate api worker` recreated those two services only; no database, Redis, LocalStack, volume, Gold/heldout fixture, Provider task, or historical evaluation artifact was changed.
- **Runtime and queue preflight.** The recreated API and Worker both reported the server-owned `analysis_task_model_max_cost` as `$0.15`. `verify-stack.ps1` exited `0`; the broker queues were empty, both workers responded, no active/reserved/scheduled tasks were reported, and durable in-flight analysis-task count was zero.
- **r39 frozen collection.** `collect-baseline-audit.ps1 -Comparison candidate -RunId candidate-p0-0-snapshot-20261018-r39 -FreezeP0CandidateSnapshot -P0CandidatePathManifest scripts/ops/p0-candidate-paths.json -RequireRuntimeSourceMatch` exited `0`. Its artifact is `artifacts/p0/candidate-p0-0-snapshot-20261018-r39/`; pytest collection exited `0` with `814 tests collected in 5.20s`. The candidate runtime-source manifest covered 79 paths with workspace SHA-256 `7b98d4262b7e091c9233dffa3f305b54dba636b5c8ca745924faee869fb553c6`; both API and Worker matched all 79 paths with zero missing or mismatched paths.
- **Scope and proof limit.** r39 repairs only r38's stale-runtime precondition. It does not rerun r37, explain the Planner's reversed comparison period or the Reviewer partial outcome, establish a comparable expected SQL-result fingerprint, prove Gold/business correctness, change the earlier full-Ruff failure classification, or approve P0.

### Automatic audit decision

- **Adopt for the next bounded investigation:** r39 is the current runtime-aligned P0 candidate precondition. **Reject P0/P0-2 completion:** r37 remains a real failed data-path observation, with `entity_scope_correct` and `outcome_correct` unresolved and SQL-result equivalence still unknown under the fail-closed comparison rule.

## 2026-10-18 — P0-2 r37 no-match evidence correction and r40 scope-order candidate (failed; P0 remains unapproved)

- **Correction to the r37 inference.** The r37 persisted result fingerprint is `4012d5a713b509655890e39fbc864ab4054cbd784178f3a0485e882309860ded`. A zero-cost call to the current `result_fingerprint_from_data_result` confirms this is exactly the canonical fingerprint for `data_result={status: insufficient_evidence, error_code: no_matching_records}`. Therefore the earlier statement that a generic Data-node success trace ruled out direct no-match was too strong: a workflow node can complete its bounded handling while its data result is still no-match. The privacy-safe trace and cleanup do not retain the generated SQL, so the precise erroneous predicate remains unknown.
- **Independent data-availability check.** Against the isolated demo business source, a read-only fixed-scope aggregate found East/delivered rows in both requested months: `2025-07` has 31 orders and CNY `2,014,010.64`; `2025-08` has 29 orders and CNY `1,847,604.72`. This proves the frozen scenario's expected source data exists. It does not prove which SQL r37/r40 generated, or authorize a fixed-query-only replacement.
- **Root-cause-only candidate.** The Planner prompt now defines the project contract for a symmetric two-month comparison: newer month is `current`, older month is `comparison`. `_canonical_symmetric_month_scope` applies that convention only when the user question contains exactly one same-year two-month pair joined by `与`/`和`/`及`/`、`, and the model supplied exactly that pair in reverse. It preserves questions using directional wording such as `相对`, month pairs that do not match the scope, and questions with additional months. This is a question-derived normalization before SQL generation, not an after-the-fact reversal of an executed result. Two new regressions cover the correction and the directional non-correction; planner/data/worker focused regression passed `77`, and scoped Ruff passed after excluding pre-existing `FLY002`/`ISC004` debt in the long Planner prompt.
- **Runtime candidate and preflight.** API and Worker alone were rebuilt/recreated; no database, Redis, LocalStack, or volume was rebuilt. `verify-stack.ps1` and queue inspection passed. r40 (`artifacts/p0/candidate-p0-0-snapshot-20261018-r40/`) collected 816 tests with exit `0`; its 79 runtime source paths matched API and Worker with zero mismatches (workspace manifest SHA-256 `55f7697e7e0f60cb1b895adf43cbcdf88d6aff7f9120a9051aabfab322e5a8ec`). Before submission, the explicit aggregate guard included r6, r3, and r37 settled cost `$0.011362`; reserving `$0.15` projected `$0.161362` under the `$0.30` cap.
- **One isolated development candidate.** Only `data-east-sales-comparison` was selected from unchanged `business_gold_v1.json` (fixture SHA-256 unchanged); the preparation manifest records `heldout_evaluation=false`, an empty document scope, API → Outbox → Worker task `139`, and a server-owned `$0.15` cap. Task `139` terminalized `partial` in `9487 ms` after four settled Provider calls and 7,338 tokens. Formal persisted-task artifact `backend/.evaluation-runs/p0-gold-data-east-sales-comparison-candidate-20261018-r40/evaluation-terminal/run.json` has SHA-256 `31f501e3852b89ba3d5bf09fa480f471faf5d68d6fd64d7074c3fd96cddfb89b`, settled cost `$0.002825`, route `data_only`, and now-correct period `2025-08 compared_to 2025-07`. The only failed check is `outcome_correct`; `sql_result_equivalent` is unknown under the fail-closed shape rule. It again has the deterministic no-match fingerprint and no confirmed facts.
- **Cleanup and boundary.** Cleanup rendered task `139`'s metadata-only trace, then removed the task, attempts, model/tool calls, events, company, user, data source, and schema snapshot; direct checks returned zero/no records for all. Cumulative recorded settled P0 measurement cost is now `$0.014187`. This candidate proves the Planner-order repair removed the entity mismatch but did not remove no-match. It does not prove the exact generated SQL defect, a safe generic SQL repair, Gold equivalence, P0 completion, or eligibility for human review.

### Automatic audit decision

- **Reject r40 as a successful data-path candidate and reject P0/P0-2 completion.** **Adopt for diagnosis:** the Planner period contract repair and the stronger conclusion that the remaining failure is an unenforced SQL-scope boundary, not missing source data. **Continue:** design one separately testable, generic execution-time scope contract for controlled free SQL; it must preserve free SQL for uncovered requests, reject scope-missing candidates before a business answer, and not hard-code this Gold case or alter Gold/heldout inputs.

## 2026-10-18 — P0-2 controlled-free-SQL comparison-scope gate r41 (mechanism passed; no new Provider run)

- **Root-cause boundary.** r40 proved that correcting the Planner's period string alone does not prevent a generated SQL candidate from yielding no matching records while the frozen source has both requested months. The prior code passed `evaluation_scope` only as untrusted-to-model prompt context; `SQLTool` enforced read-only/table scope, and `assess_metric_query` enforced registered metric lineage and mandatory filters, but neither required the candidate's `WHERE` predicate to cover a frozen comparison period.
- **Minimal execution-time gate.** `assess_metric_query` now accepts the already-validated evaluation scope. Only when all of these exist — a registered metric contract, its declared business time column, and canonical `YYYY-MM compared_to YYYY-MM` scope — it parses the free SQL with the existing SQL AST and requires that the `WHERE` predicate references that time column and covers both comparison months. It accepts either two explicit requested months or the normal closed-open range from the earlier month through the month after the later one. It does not inspect/replace arbitrary SQL, constrain CTEs/joins/aggregates, or apply to single-period, noncanonical, or scope-less requests. A missing scope match produces the existing bounded DataAgent repair path before SQL execution rather than a false business no-match.
- **Regression evidence.** New metric-contract regressions reject a one-month candidate under a frozen two-month scope and accept an equivalent closed-open two-month range. A DataAgent regression proves the first candidate is not sent to `SQLTool`, receives `metric_contract_incomplete`, and only the repaired candidate executes. Focused Planner/Data/metric/SQL-generation tests passed `81`; scoped Ruff passed after excluding the separately recorded legacy `FLY002`/`ISC004` Planner-prompt debt; scoped `git diff --check` passed (only existing CRLF warnings).
- **Runtime alignment.** API and Worker alone were rebuilt/recreated; no database, Redis, LocalStack, or volume was changed. r41 (`artifacts/p0/candidate-p0-0-snapshot-20261018-r41/`) collected 819 tests with exit `0`; API and Worker each matched all 79 runtime source paths with zero mismatches (workspace manifest SHA-256 `f148833cf140d4667a330c0faf3c25a34d748de03312a576d5a64c3e2b726df1`). Stack and queue preflight passed.
- **No paid rerun by design.** The frozen `data-east-sales-comparison` maximum is four model calls; r40 used all four across Planner, semantic review, Data, and Reviewer. A first-candidate scope repair would require another Data model call, so rerunning that exact case would not be a fair success measurement under its unchanged Gold budget. Gold/heldout files, historical artifacts, and the aggregate measured spend `$0.014187` were not changed by this slice.

### Automatic audit decision

- **Adopt:** r41's generic, fail-closed SQL comparison-scope gate and its runtime-aligned regression evidence. **Reject P0/P0-2 completion:** no post-gate real Provider observation exists, SQL-result equivalence remains unknown, and the current Gold call cap makes a repair-path rerun incomparable. **Continue:** pre-register a separate development-only repair-budget measurement contract before any Provider run; do not edit Gold to hide the cap and do not call the mechanism a successful business result.

## 2026-10-18 — P0-2 r42 privacy-safe data-path diagnostic persistence (mechanism passed; no Provider run)

- **Observed evidence gap.** r40 retained only the canonical result fingerprint after cleanup. That identifies the final `no_matching_records` outcome, but cannot distinguish a future `metric_contract_incomplete` pre-execution rejection from a SQL execution that again returns no rows. The existing persisted `result_data` can include SQL/evidence, so it is not the evaluation diagnostic source.
- **Minimal call-chain change.** `workflow.tasks._evaluation_facts` now copies only a closed set of Data-result states (`ready`, `insufficient_evidence`, `failed`, `not_run`) and an ASCII machine error code (`[a-z0-9_]{1,80}`) into the existing `evaluation_facts` object. `observation_from_persisted_task` validates those two fields before mapping them into `EvaluationObservation.actual_data_status` and `.actual_data_error_code`. The fields retain no SQL, task question, evidence rows, model output, or error text; malformed or unknown persisted values become `None` rather than being trusted.
- **Regression verification.** From `backend/`, `..\\.venv-py313\\Scripts\\python.exe -m pytest tests\\modules\\workflow\\test_worker_terminal_result.py tests\\modules\\evaluation\\test_observation.py tests\\modules\\analysis\\test_metric_validation.py tests\\modules\\analysis\\test_agents.py tests\\modules\\analysis\\test_planning.py tests\\modules\\analysis\\test_sql_generation.py -q` exited `0` with `111 passed in 2.61s`. Scoped Ruff over the changed workflow/evaluation source and tests exited `0`; scoped `git diff --check` exited `0` (only existing CRLF warnings). These are focused regression checks, not a full non-E2E or real Provider result.
- **Authorized runtime rebuild and r42.** Only `api` and `worker` were built and force-recreated; no database, Redis, LocalStack, volume, Gold/heldout fixture, historical run artifact, or Provider task was changed. `verify-stack.ps1` and queue inspection both exited `0`; queues and active/reserved/scheduled task lists were empty and durable in-flight analysis count was zero. `collect-baseline-audit.ps1` r42 collected `819` tests with exit `0`, froze 110 P0-classified paths, and matched all 79 runtime paths in both API and Worker with zero mismatches (workspace runtime manifest SHA-256 `04e7e41801b1c3513570658362de55b4e7b4a4c81fedc4b37b8494147a88202c`). Artifact: `artifacts/p0/candidate-p0-0-snapshot-20261018-r42/`.
- **Budget unchanged.** The explicit four-artifact budget guard exited `0`: settled P0 measurement spend remains `$0.014187`, with `$0.285813` remaining under the `$0.30` authorization. No paid evaluation occurred in this slice.

### Automatic audit decision

- **Adopt for diagnosis:** r42 makes the next persisted development observation distinguish the scope gate's bounded repair exhaustion from an executed no-match without reopening sensitive task data. **Continue:** before any paid run, pre-register a separate development-only repair-budget contract; do not alter Gold, select heldout input, or claim that the new diagnostic or focused tests prove a successful data-path candidate. P0 remains unapproved.

## 2026-10-18 — P0 holdout-isolation incident (no execution; P0 remains unapproved)

- **Incident.** While inspecting the frozen evaluation fixture to determine whether a separate development-only repair-budget contract can be represented without changing Gold, the operator read `backend/tests/fixtures/evaluation/business_gold_v1.json` as a whole. That file contains both development and heldout cases. This was an access-control mistake: no heldout case was selected, submitted, executed, modified, or used to tune source, but the operator has now seen heldout content.
- **Immediate containment.** No Provider call, API task, Worker task, database mutation, fixture edit, threshold edit, or cleanup action followed from the access. The fixture's SHA-256 remains the previously frozen value `a110e7c31239d7883df42608bc829ea6248902d852c544cb4ebe0bda0048cc72`. This thread must not treat the existing heldout subset as independently unseen promotion evidence. No conclusion about heldout quality is available.

### Automatic audit decision

- **Stop paid candidate progression pending operator direction.** Development-only deterministic work can continue only if it is kept separate from the exposed heldout subset. Any future promotion gate needs an explicitly authorized fresh, independently held-out evaluation version or an operator-approved contamination policy; neither may be inferred or created silently. P0 remains unapproved.

## 2026-10-18 — P0-2 per-case budget enforcement and r45 development repair diagnostic (failed; P0 remains unapproved)

- **Measurement-contract defect.** `max_model_calls` and `max_tokens` from an `EvaluationCase` had been written to the preparation manifest but were not evaluated after the persisted task completed. Therefore changing a fixture value could not actually reject an over-budget evaluation. The server-owned task model budget still protected provider spend, but the per-case measurement claim was incomplete.
- **Minimal repair and separate input.** `evaluate_threshold_contract` now rejects a selected persisted observation whose model-call count or tokens exceeds its case limit. A regression constructs both overages and receives exactly `max_model_calls` and `max_tokens`; the existing task-governance tests remain in the focused run. A new one-case development-only fixture, `business_data_east_sales_comparison_repair_development_v1.json` (SHA-256 `b60ce96dcf2d39e8d4ee8803ff2a7aedc8091c2ed7be522de398b06e6d3da4d4`), freezes the known comparison question with 5 calls and 10,000 tokens. Its threshold contract (SHA-256 `b1cdb1abe613e27e47b7473699a48a1cad9162e11f87a0c9ec99aaff1d3533d1`) requires a persisted, settled-cost observation but deliberately sets `require_hard_gate_passed=false`: this is a bounded scope-repair diagnostic, not a Gold replacement or promotion gate.
- **Regression and runtime evidence.** `pytest tests/modules/evaluation/test_thresholds.py tests/modules/evaluation/test_run_business_evaluation.py tests/scripts/test_prepare_business_evaluation.py tests/modules/runtime/test_model_governance.py tests/integration/workflow/test_task_admission.py -q` exited `0` with `49 passed in 1.66s`; scoped Ruff and JSON/diff validation passed. Only API and Worker were rebuilt/recreated. r43 is an incomplete collection artifact caused by the operator wait window expiring before checks were written; it is retained but invalid. r44 is the valid replacement: `artifacts/p0/candidate-p0-0-snapshot-20261018-r44/`, 821 tests collected with exit `0`, 112 selected P0 paths, and API/Worker each matched all 79 runtime paths with zero mismatch (workspace SHA-256 `21c8db911a701685c76cd9e069f41b65b89f5418da0960d8c56cf909ebd7f860`).
- **Preflight and isolated execution.** Immediately before submission, stack and queue checks passed with no broker work, active/reserved/scheduled tasks, or in-flight analysis task. The explicit aggregate guard accepted the fifth task's `$0.15` reservation: projected `$0.164187` under `$0.30`. The API image intentionally excludes test fixtures, so the frozen fixture, threshold contract, and corpus manifest were copied to an isolated API-container `/tmp` directory and SHA-256-checked before submission; no task was created by the first rejected image-path attempt. The harness then submitted only development case `data-east-sales-comparison-repair-v1` as task `140` via API -> Outbox -> Worker, with an empty document scope and server-owned `$0.15` cap.
- **Formal r45 result.** Task `140` terminalized `partial` in `9096 ms` after 4 settled model calls and 7,299 tokens. The persisted-task evaluation artifact is `backend/.evaluation-runs/p0-data-east-sales-comparison-repair-development-candidate-20261018-r45/evaluation-terminal/run.json`, SHA-256 `b99bd69f31c41d370f2a0150c634b29d8fc8b331b8be30ea9d82f671f7bc7018`, settled cost `$0.002779`. Its diagnostic fields are `actual_data_status=insufficient_evidence` and `actual_data_error_code=no_matching_records`; no threshold violations occurred because the observed 4/7,299 stayed within the 5/10,000 contract. The actual business hard gate still failed, solely on `outcome_correct`; no trusted success was produced. The metadata-only trace contains neither `SELECT ` nor the task question.
- **Cleanup and cost boundary.** Harness cleanup completed, rendered the trace, and direct platform checks found zero residual task, attempt, model-call, tool-call, event, temporary company, user, data-source, or schema-snapshot rows. Queue audit is idle. The five-artifact budget guard exited `0`: cumulative settled P0 measurement spend is `$0.016966`, with `$0.283034` remaining. Gold and heldout content were not changed, selected, or submitted by r45; the previously recorded holdout-exposure incident remains applicable.

### Automatic audit decision

- **Adopt:** the per-case call/token threshold enforcement, the independent development-only diagnostic fixture, and r44 runtime alignment. **Reject r45 as a business-success candidate and reject P0/P0-2 completion:** r45 proves the remaining no-match is not caused by a missing two-month scope repair or an exhausted call/token allowance, but privacy-safe artifacts still cannot identify the erroneous region/status/other SQL predicate. **Continue only with a separately designed, privacy-safe predicate-diagnostic contract or an independently reproducible source-level bad case; do not relax the no-match outcome, alter Gold, or claim any heldout or promotion result.**

## 2026-10-18 — P0-2 snapshot-filter mapping root-cause repair (mechanism passed; no Provider run)

- **Root cause traced.** The real Worker builds `SnapshotCatalog` from the task's schema snapshot and passes it to `SQLGenerationService`. The snapshot-specific prompt previously omitted the already reviewed `FILTER_VALUE_DEFINITIONS`, while the Planner scope contained the Chinese business entity `华东`. The isolated demo source stores its region code as `EAST`. r45 therefore reached a real SQL execution but could safely return `no_matching_records`; the privacy-safe persisted facts cannot reveal the original SQL literal. This is a prompt-contract omission, not evidence that the source lacks the requested rows, the two-month gate failed, or the Provider budget was exhausted.
- **Minimal repair.** The snapshot prompt now includes a registered filter mapping only when its table and column are present in the current snapshot. Its scope instruction now distinguishes the immutable business entity from the mapped database value and requires use of that mapping only when the system prompt explicitly declares it. Snapshots without a registered mapping still receive `不得猜测枚举值`. No SQL is synthesized or rewritten by application code; read-only validation, tenant scope, metric lineage, comparison-period gate, and no-match behavior are unchanged.
- **Verification and runtime.** `pytest backend/tests/modules/analysis/test_sql_generation.py backend/tests/modules/analysis/test_agents.py backend/tests/modules/analysis/test_metric_validation.py -q` exited `0` with `61 passed in 1.21s`; scoped Ruff and `git diff --check` exited `0`. Under explicit authorization, `docker compose up -d --build --no-deps api worker` rebuilt and recreated only API and Worker; both health endpoints returned `200`. A container-local prompt import assertion passed in both rebuilt services, confirming the registered `EAST = 华东` and `delivered = 已交付订单` mappings are present. No database, Redis, LocalStack, volume, fixture, historical evaluation artifact, task, or Provider call was changed.

### Automatic audit decision

- **Adopt for the next development-only measurement:** the source-level snapshot prompt repair and rebuilt API/Worker runtime alignment. **Reject P0/P0-2 completion and any business-success claim:** the repaired prompt is deterministic mechanism evidence, not a real API -> Outbox -> Worker Provider result. **Continue only after a fresh no-cost queue/budget preflight and a separately authorized development-only run; do not touch Gold or the exposed heldout subset.**

## 2026-10-18 — P0-2 r46 snapshot-filter mapping candidate freeze (precondition passed; no Provider run)

- **Candidate capture.** r46 at `artifacts/p0/candidate-p0-0-snapshot-20261018-r46/` passed its required static collection: `822 tests collected in 3.26s` with exit `0`. The explicit P0 manifest now includes the changed snapshot-prompt regression test; it selected 113 P0-classified changed paths (manifest SHA-256 `e9ca4f6c1b51b7d69f5910fa08cea74bb299afee4cda10b37a69359ed7fc6b1c`). Historical `backend/.evaluation-runs`, `output/`, and documents remain excluded from the candidate payload.
- **Runtime-source alignment.** The collector's required runtime fingerprint covered 79 runtime paths with workspace SHA-256 `0c85d6ca2a2867e77dcf71e801afffa985403c19451117078ca2b7996b0774b1`. Both rebuilt API and Worker containers matched `79/79`, with zero missing or mismatched paths; the collector exited `0`. This is stronger than the targeted container import check but still only proves source-image alignment.
- **Boundary.** No queue preflight, Provider call, API task, Worker task, database/Redis/LocalStack action, fixture selection, or cost change occurred in r46. Full Ruff and the historical non-E2E suite were deliberately not run; their known status is unchanged.

### Automatic audit decision

- **Adopt:** r46 as the current runtime-aligned candidate snapshot for this root-cause repair. **Reject P0/P0-2 completion and business-success claims:** a frozen, source-aligned candidate and focused regressions do not establish model behavior or a successful persisted-task outcome. **Continue:** request/perform the already-authorized development-only preflight before deciding whether one capped Provider diagnostic is warranted; do not use Gold or heldout input.

## 2026-10-19 — P0-2 r47 snapshot-filter mapping development diagnostic (mechanism behavior passed; promotion gate unknown)

- **Preflight and input integrity.** Before submission, stack verification passed, broker queues were `0`, active/reserved/scheduled tasks were empty, and no analysis task was in flight. The explicit five-run cost guard recorded settled spend `$0.016966`; reserving the single server-owned `$0.15` task projected `$0.166966`, under the `$0.30` authorization. The independent development-only fixture, threshold contract, and corpus manifest were copied to an isolated API-container directory and SHA-256-verified (`b60ce…3d4d4`, `b1cdb…533d1`, and `1307b…841148` respectively). No Gold or heldout case was selected or submitted.
- **One bounded real run.** Task `141` was submitted through API -> Outbox -> Worker with the rebuilt r46 image, empty document scope, the `$0.15` server cap, and `max_model_calls=5` / `max_tokens=10000`. It reached terminal `completed`. Its persisted-task evaluation run is `backend/.evaluation-runs/p0-data-east-sales-comparison-repair-development-candidate-20261018-r47/evaluation-terminal/run.json`; it records `data_status=ready`, `outcome=completed`, duration P95 `9979 ms`, five model calls, 9,153 tokens, and settled provider cost `$0.003422`. Threshold violations are empty.
- **Outcome dimensions and hard gate.** Route, entity scope, terminal outcome, numeric consistency, deterministic validation, persisted report, and security gate all passed; there are no violations. The sole `unknown_checks` entry is `sql_result_equivalent`: this development fixture deliberately specifies a scenario-shaped expected fingerprint whereas persisted data results retain only a SHA-256 value. Thus r47 proves the snapshot-filter mapping removed the prior no-match failure, but does not establish comparable source-result equivalence or a promotion-quality pass. No fixture, including Gold, was changed to accommodate the result.
- **Cleanup and privacy.** Cleanup completed after terminal capture. Direct platform checks returned zero task, execution-attempt, model-call, tool-call, workflow-event, temporary company, user, data-source, and schema-snapshot rows. Queue inspection was again idle. The rendered trace contains neither `SELECT ` nor the question text.

### Automatic audit decision

- **Adopt for diagnosis:** r47 is a real, bounded development-only API -> Outbox -> Worker result showing the mapping repair fixes the no-match behavior under the frozen input and resource contract. **Reject P0/P0-2 completion and promotion:** result equivalence is fail-closed `unknown`, not pass. **Continue:** derive a separately reviewable, source-level expected-result fingerprint method before any comparable development promotion measurement; do not retrofit r47's observed hash into its frozen fixture, alter Gold, or use heldout input.

## 2026-10-19 — P0-2 registered comparison-query type repair and source-fingerprint boundary

- **Reproduced source-query defect.** The first attempt to execute the existing registered `regional_revenue_comparison` query against the real read-only demo source failed in PostgreSQL with `AmbiguousParameter`: `region` appeared in both `IS NULL` and `=` without a resolvable parameter type. The existing unit test only mocked the executor, so it could not expose PostgreSQL type inference.
- **Root-cause-only repair.** The registered SQL now explicitly casts that controlled `region` parameter to `text` in both uses. A new assertion first failed against the old query string and then passed. The focused template-query, SQL-generation, and business-evaluation suites passed `71`; scoped Ruff, JSON validation, and diff validation passed. API and Worker alone were rebuilt/recreated; readiness returned `200`; the rebuilt API executed the registered query successfully with five columns and one row. No Agent route was replaced with this fixed query.
- **Result-equivalence boundary established.** A source-derived SHA-256 was computed in memory only after applying the same deterministic JSON-safe value conversion as DataAgent. It differs from r47's persisted SHA-256 even though r47 passed route, scope, outcome, numeric, deterministic, persistence, and security checks. This establishes that the remaining `sql_result_equivalent=unknown` is structural: the unrestricted Agent result and the registered comparison query have different output shapes. Neither hash was added to or substituted into a fixture.

### Automatic audit decision

- **Adopt:** the PostgreSQL type fix and its real read-only execution proof. **Reject:** using the registered-query hash as r47's expected result, treating the hashes as comparable, or claiming P0 completion. **Continue:** define an explicit semantic projection contract for comparable data results, or retain result equivalence as unknown; it must be source-derived, versioned, and tested without making free SQL fixed-query-only.

## 2026-10-19 — P0-2 r48 registered-query repair candidate freeze (precondition passed; no Provider run)

- r48 at `artifacts/p0/candidate-p0-0-snapshot-20261019-r48/` collected pytest successfully with exit `0`. The expanded explicit P0 manifest selected 115 current candidate paths; it now includes the registered query and its regression test.
- The required runtime fingerprint covered 80 API/Worker runtime paths with workspace SHA-256 `6babce8456375a3e503f4d27cd8fda6264eb893f4643ca551de359276882ff4e`. API and Worker both matched `80/80`, with zero missing or mismatched paths; runtime status is `passed`.
- This proves only source-image alignment for the registered-query type repair. It did not submit a Provider task, alter a fixture, establish semantic result equivalence, clear the r47 unknown hard gate, or approve P0.

### Automatic audit decision

- **Adopt:** r48 as the current runtime-aligned candidate snapshot. **Reject P0/P0-2 completion:** the source result and Agent result remain structurally incomparable under the current result-fingerprint contract. **Continue:** create a separately reviewed semantic projection only if its source derivation and free-SQL applicability can be specified without weakening the result-evidence boundary.

## 2026-10-19 — P0-2 r49 semantic revenue-comparison projection (mechanism passed; no Provider run)

- **Root cause and contract.** r47's persisted free-SQL result and the registered comparison query answer the same two-month `revenue/v1` question but have different result shapes, so their raw SHA-256 values must remain incomparable. The new projection accepts only one `ready` evidence item with a supported `revenue/v1` metric assessment, exactly two distinct columns (one recognized month alias and one recognized revenue alias), exactly the two requested canonical months, two distinct rows, and values exactly representable to CNY cents. Any malformed, extra, duplicate, noncanonical, unsupported-metric, or missing input yields no semantic fingerprint and therefore keeps the hard gate `unknown`.
- **Source-derived development contract.** The expected semantic SHA-256 in the new development-only v2 fixture was derived from one execution of the existing registered read-only comparison query for the frozen `EAST` / July-August 2025 parameters. The command retained only query success, five-column/one-row shape, and the resulting hash; it did not write returned source values to the fixture, artifact, or ledger. The new fixture SHA-256 is `c09d29e0e6e12dfa86c5d59b2d7a11e717c95efbb114698438f8e8f02b562fb4`; its paired threshold remains a one-case development diagnostic with the existing `$0.15` ceiling and `require_hard_gate_passed=false`. v1 and r47 artifacts were not changed.
- **Call-chain change.** `workflow.tasks._evaluation_facts` persists the additional hash only; `observation_from_persisted_task` validates and maps it; `evaluate_case` uses it only when the frozen case explicitly supplies an expected semantic fingerprint. The raw result fingerprint remains intact for every other case. This does not change SQL generation, SQL validation, database permissions, result rows, or the free-SQL execution path.
- **Verification and authorized runtime rebuild.** Focused regression tests for semantic normalization/fail-closed behavior, evaluator selection, persisted observation, threshold freeze, Worker persistence, template query, and SQL-generation completed with `116 passed in 2.03s`; scoped Ruff passed; `git diff --check` found no whitespace errors (only existing unrelated CRLF warnings). Under authorization, `docker compose up -d --build --no-deps api worker` rebuilt and recreated only API and Worker. API readiness returned `200`; the rebuilt API's registered-query projection produced the frozen semantic hash; Worker imported the new function and its log reached `ready`. No database, Redis, LocalStack, volume, migration, Gold/heldout fixture, historical evaluation artifact, API task, or Provider model call was changed.
- **r49 candidate freeze.** `artifacts/p0/candidate-p0-0-snapshot-20261019-r49/` collected pytest with exit `0`. Its explicit P0 manifest records 116 candidate paths. Its required runtime fingerprint covers 80 API/Worker source paths; both services matched `80/80`, zero missing/mismatched, with workspace runtime SHA-256 `76ced19151acad4473407c0c362f9f41ee2cbe9713f551b13232ea3ba9ed06a5`.

### Automatic audit decision

- **Adopt for the next independent development-only measurement:** the strict, versioned semantic projection and r49 source-image alignment. **Reject P0/P0-2 completion and a business-success claim:** no fresh persisted Agent result has yet exercised the new Worker field and v2 frozen contract; r47 remains historically `unknown` for result equivalence. **Continue only with a separately preflighted, capped development v2 API -> Outbox -> Worker run; do not alter Gold, use heldout input, or treat the projection's unit/runtime checks as an end-to-end pass.**

## 2026-10-19 — P0-2 r50 semantic-projection development diagnostic (passed; P0 remains unapproved)

- **Preflight and isolation.** With the r49-built API and Worker already ready, stack verification passed; both broker queues were `0`; both Workers had no active, reserved, or scheduled task; and durable in-flight work was `0`. The lone historical `analysis_outbox:worker_claimed:1` belongs to task `114` in `awaiting_review`, not the r50 scope, and was not modified. The v2 development fixture SHA-256 matched its threshold contract (`c09d29e0e6e12dfa86c5d59b2d7a11e717c95efbb114698438f8e8f02b562fb4`); its empty corpus manifest was separately frozen and copied into the isolated API path. No Gold or heldout input was read, selected, changed, or submitted.
- **One bounded real run.** Exactly one disposable API -> Outbox -> Worker task (`142`) ran the v2 development case with the server `$0.15` task cap, `max_model_calls=5`, and `max_tokens=10000`. It reached `completed` in `9,091 ms`, made five model calls, consumed 9,084 tokens, and settled `$0.003351`; no unknown/reserved billing state is reported by the evaluator.
- **Persisted outcome.** The terminal evaluator records `1/1` passed, zero failed/unknown, hard gate `passed`, and no case violations or unknown checks. Its strict semantic result equivalence, numeric consistency, deterministic validation, security gate, report persistence, terminal outcome, and budget all passed. The raw result fingerprint was intentionally not used for this v2 comparison. Artifacts are retained at `backend/.evaluation-runs/p0-data-east-sales-comparison-semantic-development-candidate-20261019-r50/evaluation-terminal/` (`run.json` SHA-256 `e2c0aa08e98078b56abc50a6dee5388c3cee8dd7d851a4a13d4af57a753ab5b4`; `report.md` SHA-256 `7c9e6365bac645d7cf6ebaf7b381a2bee41e9e0b1b8fa91546aef0fa024e2b7f`) and `traces/task-142.html` (SHA-256 `909fd8eadb5766ee4a975f1230c8785c92f3b06a4d8fa7af253bd4d1212db949`).
- **Cleanup and accounting.** Cleanup completed only after terminal artifacts were copied. Direct platform queries returned zero rows for r50 task `142`, temporary company `100`, user `108`, data source `76`, schema snapshot `73`, and membership `99`. The seven-run settled-cost guard passed at `$0.023739`, with `$0.276261` remaining against the authorized `$0.30` evaluation ceiling. Final stack verification passed and both queues remain empty.

### Automatic audit decision

- **Adopt for this narrow development contract:** r50 provides real persisted API -> Outbox -> Worker evidence that the strict semantic projection recognizes the frozen two-month `revenue/v1` result without weakening free-SQL execution or the existing raw fingerprint. **Reject P0/P0-2 completion, baseline promotion, and a general business-success claim:** this is one development case, the prior heldout exposure prevents independent promotion use, and it does not establish broader task quality, recovery behavior, or production capacity. r47 remains historically `unknown` under its former raw-fingerprint contract.

## 2026-10-19 — P0 non-E2E baseline repair: restore-drill subprocess encoding (passed; P0 remains unapproved)

- **Observed baseline failure.** The first current-candidate `pytest tests -q -rs -m "not e2e and not slow"` run reached `814 passed, 2 failed, 4 skipped, 7 deselected` (exit `1`). Both failures were the restore-drill script tests, and both failed while evaluating their own error-message assertion: Python decoded the `pwsh` child process with the host `cp950` default, a reader thread raised `UnicodeDecodeError`, `stderr` became `None`, and `result.stdout + result.stderr` raised `TypeError`. The intended PowerShell guard did run before any database access; the isolated checksum-mismatch case reproduced this same failure deterministically.
- **Root-cause-only repair.** `tests/scripts/test_restore_drill_script.py` now follows the existing P0 budget-script subprocess pattern: it explicitly sets the PowerShell console output encoding to UTF-8 and captures output with Python `encoding="utf-8", errors="replace"`. No restore command, database-selection guard, backup manifest rule, database, container, or production path changed. The two existing tests supplied the red state; after the change `pytest tests/scripts/test_restore_drill_script.py -q` exited `0` with `2 passed`, and scoped Ruff plus `git diff --check` exited `0`.
- **Current candidate baseline.** The full non-E2E command then exited `0` with `816 passed, 4 skipped, 7 deselected in 35.68s`. The four skips remain explicitly dependency-bound (two opt-in LocalStack proofs and two Docker business-database SQL-executor proofs); they are not counted as passes. Full-worktree Ruff was not run and its previously classified debt is unchanged.
- **r51 candidate capture.** `artifacts/p0/candidate-p0-0-snapshot-20261019-r51/` collected `827` tests with exit `0`, freezes `119` P0-classified candidate paths, and records snapshot-manifest SHA-256 `fe218140539104711f45c7afff65194790d3097b0f750e567de5f9e2c9b6968e`. Its required runtime fingerprint covers `80` API/Worker paths; both services matched with zero mismatches and workspace SHA-256 `76ced19151acad4473407c0c362f9f41ee2cbe9713f551b13232ea3ba9ed06a5`. No API/Worker rebuild was needed because only a test helper changed.

### Automatic audit decision

- **Adopt for the current non-E2E measurement baseline:** the UTF-8 subprocess-capture repair, green restore-guard regressions, and r51 candidate snapshot. **Reject P0 completion, full static cleanliness, E2E completeness, and baseline promotion:** the four dependency skips remain unproved, known global Ruff debt remains, and P0 still lacks an uncontaminated heldout promotion path plus the broader frozen-set/repeatability evidence. No Provider call, Gold/heldout selection, runtime task, database restore, or service rebuild occurred in this slice.

## 2026-10-19 — P0-3 r52 comparable development repeat (functional gates passed; latency threshold failed; P0 remains unapproved)

- **Frozen development input and bounded execution.** r52 used only the development case `hybrid-east-delivered-revenue-causality-boundary`, frozen fixture SHA-256 `c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c`, the r3 comparison threshold contract, and the unchanged corpus manifest SHA-256 `1307b4f130b70bda39a16f6e2f5e60ba24c18eb8b9fa515ea8254f265d841148`. Stack/queue preflight was idle before submission; task `143` used the server-side `$0.15` cap, six model calls, 11,010 tokens, and settled `$0.004268`. No Gold or heldout fixture was read, selected, changed, or submitted.
- **Approved human-review path was exercised.** The persisted draft first passed deterministic schema validation, frozen citation-scope validation, cost settlement, and the exact frozen-case evaluator precheck. It contained one confirmed fact, one hypothesis, one document finding, one citation, zero limitations, and one recommendation. Review request `13` was then approved by the existing company owner through `approve_review_request`; Worker published the already-validated draft via its `review_publish_only` path. Task `143` reached `completed/completed`. This approval happened after the precheck; it is not an independent human business-judgment sample.
- **Terminal evaluation versus frozen threshold.** The persisted-task evaluator records `1/1` passed, zero failed/unknown, hard gate `passed`, terminal outcome/numeric consistency/result equivalence/deterministic validation/security/report persistence/budget all passed, and no case violations or unknown checks. However, the evaluation command correctly failed its threshold contract on `duration_p95_multiplier`: r52 total duration P95 was `476,933 ms`, while r3 baseline was `76,587 ms` and its authorized `1.2` ceiling is `91,904.4 ms`. The measured total includes the review wait, so it cannot be represented as a successful comparable latency result. The terminal artifacts are `backend/.evaluation-runs/p0-development-single-r3-repeat-candidate-20261019-r52/evaluation-terminal/run.json` (SHA-256 `f76918be87f5e81e4ea6ba407a0a7ca291cecc2539a68cd0733c5fb42528a6e4`) and `report.md`; their normalized-observation scope remains insufficient by itself to prove every runtime dependency invocation.
- **Cleanup, trace, and accounting.** Cleanup completed after terminal capture. Direct platform checks returned zero rows for r52 task `143`, temporary company `101`, data source `77`, schema snapshot `74`, user `109`, membership `100`, and document `53`; final stack verification passed. The cleanup manifest names `/tmp/p0-r52/output/traces/task-143.html`, but that file was absent when copied, so r52 has no retained rendered trace and this is an evidence gap. The explicit eight-run settled-cost guard passed at `$0.028007`, leaving `$0.271993` against the authorized `$0.30` total; r52's final budget record is `backend/.evaluation-runs/p0-development-single-r3-repeat-candidate-20261019-r52/budget-final.json` (SHA-256 `fe184c3b0e0387ad59fbabc690e38c1d7760c9e3a5259bce8d81a11cecfe24d3`). No additional Provider call was made after r52.

### Automatic audit decision

- **Adopt as narrow workflow-correctness evidence:** r52 confirms this frozen development case can traverse API -> Outbox -> Worker -> deterministic review gate -> approved publish with settled cost and all persisted outcome/security checks passing. **Reject P0-3 latency pass, baseline promotion, and P0 completion:** the frozen P95 multiplier failed, the wait-inclusive timing makes this run non-comparable as a performance success, its trace is unavailable, it is one development case, and heldout has prior exposure. **Continue only after a separately reviewed measurement design distinguishes machine processing time from authorized human-review wait; do not alter the frozen r3 result, retrofit the threshold, submit another Provider run, or use Gold/heldout merely to obtain a pass.**

## 2026-10-19 — P0-3 timing-semantics repair and v2 threshold contract (mechanism passed; no new Provider run)

- **Observed call-chain defect.** `workflow.tasks._save_workflow_result` completes the first `TaskExecutionAttempt` when a report enters `awaiting_review`; approval preserves the task's original `started_at`; `workflow.tasks._publish_approved_draft` then overwrites `AnalysisTask.duration_ms` using first claim through final publication. `observation_from_persisted_task` previously mapped that total directly to `EvaluationObservation.duration_ms`, and `evaluate_run` used it for the P95 comparison. Therefore r52's `476,933 ms` necessarily included the authorized human decision wait and was not a machine-processing performance measurement.
- **Minimal derived telemetry, no migration.** `duration_ms` remains the end-to-end lifecycle fact. The persisted-observation adapter now derives `machine_execution_duration_ms` by summing complete `TaskExecutionAttempt` ownership intervals, and `human_review_wait_ms` from `ReviewRequest.created_at` through `reviewed_at`. Missing/inverted timestamps fail closed to `None`; no review request yields zero review wait. This reads existing durable timestamps only; no schema, API, queue, task, report, or permission behavior changed.
- **Frozen threshold semantics.** Existing `p0-evaluation-thresholds-v1` contracts preserve their end-to-end P95 behavior exactly. New `p0-evaluation-thresholds-v2` accepts the same frozen baseline hash and cost-per-trusted-success gate but compares only `machine_execution_duration_p95_ms` at the configured multiplier; it explicitly rejects end-to-end duration thresholds. The regression proves a `70,000 ms` lifecycle with `14,000 ms` Worker activity and `53,000 ms` review wait remains distinguishable, and that a `60,000 ms` review wait does not influence v2's 1.2 machine-time comparison.
- **Verification and runtime alignment.** Evaluation-module regression ran `118 passed, 2 skipped` in `2.53s`; focused Ruff passed after excluding only pre-existing executable-bit rule `EXE002`, and scoped `git diff --check` passed with only existing CRLF notices. Under authorization, only API and Worker were rebuilt/recreated; API readiness returned `200`, both services imported the new metric/contract fields, and r53 (`artifacts/p0/candidate-p0-0-snapshot-20261019-r53/`) collected `827` tests with exit `0`. Its runtime fingerprint covers 80 paths and both API/Worker match all 80 with zero mismatches (workspace SHA-256 `c49257c46674f4eb2fdac5ab73ca5517fcfd788cd054dc52e89912748d8d4ec3`). A full non-E2E suite was started twice but this execution environment retained only partial progress output and no exit code; it is `unknown`, not a passing result.

### Automatic audit decision

- **Adopt for a new measurement baseline only:** the separated, fail-closed timing semantics and v2 contract mechanism. **Reject any reinterpretation of r3 or r52:** old artifacts lack the new machine-time metric, and r52's temporary execution rows were cleaned; neither can be retrofitted into a v2 baseline. **Continue:** freeze a development-only v2 baseline input and, only after its real persisted run and cleanup, freeze a candidate contract referencing that baseline; do not use heldout/Gold, submit a Provider run, or claim a P95 improvement before those separate artifacts exist.

## 2026-10-19 — P0-3 r55/r57 machine-duration baseline and candidate (development comparison passed; P0 remains unapproved)

- **Separate, frozen baseline/candidate.** r55 used the frozen development hybrid case (fixture SHA-256 `c49302f19cc6ddeece23ae150786f13e3d62c12bd0945c5d8e8153c12eb1083c`) under the v2 baseline contract. Its persisted result passed `1/1`, hard gate, deterministic validation, scope, outcome, cost, and report persistence; it recorded total P95 `153,321 ms`, machine-execution P95 `78,288 ms`, review-wait P95 `73,162 ms`, six calls, 10,915 tokens, and settled `$0.004210`. Its terminal run SHA-256 is `dbb6efc142e7f97a9b40558748830263dea7abb0bc03bb0907c0075ec7cca600`.
- **Candidate comparison passed the intended metric.** r57 froze that exact r55 SHA in `p0-evaluation-thresholds-v2` with machine-duration and cost-per-trusted-success multipliers both `1.20`. It passed `1/1` with no violations or unknown checks: total P95 `96,633 ms`, machine-execution P95 `8,245 ms` (below the `93,945.6 ms` machine-time limit), review-wait P95 `85,628 ms`, six calls, 10,926 tokens, and settled `$0.004206`. The terminal artifact is `backend/.evaluation-runs/p0-development-machine-duration-candidate-20261019-r57/evaluation-terminal/run.json` (SHA-256 `cf57129b1fa1dc0ec3821e8aa9cd8456ecec1e212067669c761ee955eb27f2ee`). The lower candidate machine time is one development observation, not a stable performance improvement claim.
- **Review, cleanup, and costs.** Both tasks were approved only after read-only checks of draft schema, frozen citation scope, deterministic validation, frozen-case evaluation, and settled cost; approval used the existing approved owner and publish-only Worker path. Cleanup after terminal capture returned zero rows for r55 task/company/data-source/snapshot/user/member/document `144/102/78/75/110/101/54` and r57 `145/103/79/76/111/102/55`. r56 candidate freeze collected 827 tests and matched API/Worker runtime sources 80/80. The explicit ten-run cost guard passed at `$0.036423`, leaving `$0.263577`; no Gold or heldout case was read, changed, or submitted.

### Automatic audit decision

- **Adopt narrowly:** r55/r57 establish that the new v2 contract measures Worker ownership intervals separately from human review wait and that this one frozen development candidate satisfies the authorized 1.2 machine-P95 and cost multipliers. **Reject P0 completion, promotion, production-performance claims, and heldout use:** there is only one baseline/candidate development pair, r52 lacks a retained trace, the full current non-E2E exit remains unknown, and heldout was previously exposed. **Continue with non-paid verification or a separately authorized repeatability design; do not treat human-review wait as a machine regression or weaken v2 back to end-to-end P95.**

## 2026-10-19 — Current non-E2E regression baseline after timing-contract changes (passed; does not prove E2E)

- **Complete bounded execution.** The previous single-command full-suite attempt lost its exit code to the host execution window, so it was not counted. The same `not e2e and not slow` selection was then executed in disjoint directories with explicit exits: `tests/modules` `707 passed, 2 skipped, 2 deselected`; `tests/integration` `90 passed, 2 skipped, 5 deselected`; `tests/scripts` `23 passed`. Together this is `820 passed, 4 skipped, 7 deselected`. Current collection reports `831 tests collected in 3.12s`.
- **Skip boundary.** The four skips are not passes: two require the Docker business database SQL-executor proof and two require opt-in LocalStack object-storage E2E. No Provider task, tenant, fixture, Gold/heldout input, queue, database restore, or service rebuild occurred during this regression verification.

### Automatic audit decision

- **Adopt:** current non-E2E regression is now evidence-backed rather than unknown. **Reject E2E/production claims:** dependency-bound skips and all real-scale/service-failure behavior remain outside this result. **Continue:** freeze and, under the existing capped authorization, measure a separately labeled v2 development repeat if repeatability evidence is required; do not fold this regression into a business-quality or heldout conclusion.

## 2026-10-19 — P0-3 r59 second v2 development repeat (passed; limited repeatability evidence)

- r58 candidate freeze collected successfully and matched API/Worker runtime sources with zero mismatches. Under the same frozen development fixture, corpus, r55 baseline SHA, `$0.15` per-task cap, and v2 1.2 multipliers, task `146` passed 1/1 with hard gate `passed`, no violations/unknown checks, six model calls, 11,026 tokens, and settled `$0.004308`.
- The repeat records machine-execution P95 `8,904 ms`, human-review wait P95 `39,231 ms`, and end-to-end P95 `51,871 ms`; only the first is compared to r55's machine P95. The v2 threshold contract reports no violation. This is a second development repeat, not independent heldout evidence.
- Cleanup returned zero rows for task/company/data-source/snapshot/user/member/document `146/104/80/77/112/103/56`. No new Provider task was submitted afterward.

### Automatic audit decision

- **Adopt narrowly:** r57 and r59 are two successful development repeats under the same frozen v2 contract, both separating human wait from machine time. **Reject P0 completion, production performance, and independent generalization claims:** the comparison remains one development case, no uncontaminated heldout promotion input exists, and E2E dependency skips remain unproved.

## 2026-10-19 — A2b split-metadata audit (no Gold content read)

- **Method and scope.** The audit enumerated evaluation-fixture filenames and parsed only files whose filenames contain `development`; it did not open, select, change, or submit `business_gold_v1.json` or `p0_gold_data_east_sales_comparison_baseline_thresholds.json`. It then flattened each development fixture's `cases[]` metadata and counted `case_id` and `split`. Threshold-only development JSON files were excluded because they contain no `cases[]`.
- **Observed inventory.** The development fixtures contain 42 case records representing exactly 30 unique `case_id` values, and every one declares `split=development`. Four knowledge case IDs occur in four fixture versions each; these are versioned records, not additional unique cases. This verifies the current development-side count, but it does not establish dimension coverage or the contents/count of the unopened Gold files.
- **Plan comparison.** A2b requires 30 unique cases partitioned into 23 development and 7 heldout cases, with one heldout case per principal dimension. Therefore the current inventory does not satisfy the A2b split requirement. The previously exposed heldout material cannot be relabeled as an independent promotion set.

### Automatic audit decision

- **Reject A2b/P0 completion and heldout-based promotion:** the required independent 7-case holdout split is not presently evidenced. **Continue only with a separately authored, access-controlled holdout process that keeps its case contents outside this optimization context; do not convert existing development cases, inspect the exposed Gold contents, or claim independent generalization from r55/r57/r59.**

## 2026-10-19 — r59 local artifact and budget-ledger completion (no new evaluation)

- The existing API-container `prepare.json` for r59 was copied to its current run directory after confirming the source file existed; its host SHA-256 is `bbde7df94046d2b0985bba708d4905edc1d20f010cb2fa2ff03e8b31ef37e966`. No task, queue item, fixture, database row, or Provider call was created.
- `assert-p0-evaluation-budget.ps1` then read the eleven distinct settled terminal-run artifacts in the current authorized budget ledger. It exited `0`: settled/projected cost is `$0.040731`, planned cost is `$0`, and remaining cost against `$0.30` is `$0.259269`. The compact result is retained at `backend/.evaluation-runs/p0-development-machine-duration-repeat-20261019-r59/budget-final.json`.

### Automatic audit decision

- **Adopt only the accounting/artifact closure:** r59 is now locally self-contained and the cumulative cap remains unexceeded. **Reject any quality or promotion conclusion from this bookkeeping step:** A2b's independent holdout requirement, dependency-bound E2E evidence, and broader P0 exit gates remain unresolved.

## 2026-10-19 — Correction: A2b inventory scope and holdout-access boundary

- **Correction to the prior split-metadata audit.** Its 30 unique, all-`development` count covers only separately named development fixtures; it is not an audit of `business_gold_v1.json`. Source-level tests declare that the designated Gold fixture is intended to contain 30 unique cases split 23 development / 7 heldout, with one heldout primary-dimension case each, but those assertions are not current-file proof because Gold contents were deliberately not read or executed in this slice. The earlier conclusion that the complete current evaluation inventory has no 23/7 split is therefore withdrawn.
- **What remains proved.** The separately named development-fixture pool has 30 unique case IDs, all with coverage tags; its observed complexity mix is 10 simple, 14 medium, and 6 complex. This is useful development-pool metadata only, not an independent evaluation-set or coverage-compliance result.
- **Access-control finding.** `scripts/run_business_evaluation.py` accepts an arbitrary `--fixture`, reads all fixture bytes, selects any requested case IDs, and serializes the selected IDs into its run artifact. Threshold validation checks fixture hash, case count, and split, but does not provide an access-controlled opaque-holdout interface. Consequently an existing Gold file available in this checkout cannot constitute an unexposed independent promotion set for this optimizer, regardless of its declared split.

### Automatic audit decision

- **Reject P0/A2b completion and independent promotion:** the intended 23/7 shape is source-declared but the existing Gold set is already exposed, and the current CLI has no blind-holdout boundary. **Continue only after an independently authorized holder supplies a sealed holdout workflow or executes it outside this optimization context; do not read the present Gold contents, run its tests, or label its existing split as independent evidence.**

## 2026-10-19 — Evaluation-isolation incident: Gold content exposure during documentation search

- A broad source search intended to find an existing sealed-holdout handoff workflow omitted an exclusion for `backend/tests/fixtures/evaluation/business_gold_v1.json`. The command output included existing Gold fixture content in this optimization context. No fixture was changed, no evaluation was submitted, no task/queue/database state changed, and no Provider call occurred.
- The search result must not be used for tuning, case selection, prompt construction, threshold adjustment, or a success claim. This incident independently confirms that the repository-resident Gold fixture is not an unexposed holdout for the current optimizer. Subsequent searches must exclude Gold fixture paths explicitly rather than relying only on directory-level assumptions.

### Automatic audit decision

- **Reject existing-Gold independence and any heldout-based P0 promotion:** this exposure is recorded as a contamination event, not as an evaluation result. **Continue only through a new independently held sealed set or an external holder-operated workflow; do not retry, inspect, or repair the existing Gold set to obtain a passing result.**


## 2026-10-19 — 执行计划切换与仓库目录重构（结构调整，无行为变更）

- **计划**：用户确认采用 `docs/plans/improvement_and_learning_plan.md`（全模块企业生产标准改造 + 生产能力培养）；AGENTS.md“当前执行优先级”同步，原核心优先计划移入 `docs/plans/history/`。
- **基线提交**：`140007c1` 将此前累积的未提交改动（147 个文件）提交为重构前基线；提交前 `tests/modules + tests/scripts`（not e2e/slow）730 passed / 2 skipped。本地评测运行产物（`.evaluation-runs/`）改为忽略；个人简历文件移出仓库并停止跟踪（已推送的历史中仍存在）。
- **目录调整**：`backend/requirements/`、`backend/docker/`、`backend/scripts/{data,evaluation,ops,db}`、`backend/tests/unit`（原 `tests/modules`）、`data/business_knowledge_base`（原 `docs/` 下）、`docs/{plans,architecture,design,operations,audits}`；`workflow` 拆为 `orchestration/lifecycle/delivery/audit`，`analysis` 拆为 `planner/data/catalog/metrics`，`input_artifacts` 拆为 `upload/processing`。Celery 任务模块（`tasks.py`、`outbox_tasks.py`）保持原位，任务名不变。说明见 `docs/architecture/modular_monolith_structure.md`。
- **验证**：全部 `app` 模块逐个导入 0 失败；旧模块路径扫描 0 残留；`tests/unit + tests/scripts` 730 passed / 2 skipped / 2 deselected（与调整前一致）；`tests/integration` 90 passed / 2 skipped / 5 deselected（隔离库 `agent_platform_test`，与 10-19 先前记录一致）；`docker compose config -q` 通过。
- **镜像**：`docker compose build api worker` 使用新 `backend/docker/*.Dockerfile` 与 `requirements/` 构建成功（退出码 0）。
- **未证明**：正在运行的容器尚未用新镜像重启，未做重启后的全链冒烟；evaluation 镜像未构建；E2E/slow 测试未运行；ruff 在调整前即有 343 项问题，本次未处理（属阶段 1 工程基础）；evidence 历史条目中的旧路径文本保留原样，作为历史记录。

## 2026-10-19 — 阶段 1 工程基础：当前静态与前端构建基线（进行中）

- **当前事实**：当前 HEAD 为 `f00ea13a`；计划起草时的 `a0d8578a` 与 147 个未提交文件已明确标记为历史快照。仓库没有 `.github/` 工作流或 pre-commit 配置；`backend/pyproject.toml` 声明 Python `>=3.10,<3.15`，而 Dockerfile 与 `pyrightconfig.json` 以 Python 3.12 为准。前端存在 `package-lock.json`。
- **验证**：在 `backend/` 运行 `..\\.venv-py313\\Scripts\\python.exe -m ruff check app tests scripts --output-format concise` 退出 `1`，报告 `378` 项；其中 `204` 项可用安全 `--fix` 自动修复，剩余项包括 API 依赖注入规则、盲捕获异常和闭包循环变量等，需要逐类设计而非批量修改。`frontend/` 的 `npm run build` 退出 `0`。`npm ci --dry-run` 退出 `0`。
- **边界**：这不是阶段 1 完成声明。尚未建立 CI、未将 Pyright 纳入可复现依赖安装、未决定 lint 债务的分批门禁策略，也未重新验证 E2E/slow 或容器重启后的完整链路。

### 当前决策

- **继续**：先由用户完成工程基础的 12 问设计练习，再共同确定 CI 的最小职责、Python 3.12 环境、静态检查策略和分批还债边界。不得用 `ruff --fix` 批量覆盖行为类规则，或以通过前端构建宣称后端工程门禁已达标。

## 2026-10-19 — 阶段 1 工程基础：lint 分类与前端测试跟进（进行中）

- **分类**：378 项 Ruff 结果中，`I001` 164 项、`B008` 116 项、`ISC004` 19 项、`FURB157` 13 项；机械可修复项不能替代对行为规则的逐项审查。前端 `npm test` 退出 `0`，2 个测试文件、7 个测试通过。
- **B023 复核**：`backend/app/modules/input_artifacts/outbox_tasks.py:53` 的 lambda 捕获 `task` 被 Ruff 标记为 `B023`，但 `publish_artifact_processing_event` 在同一调用栈的第 248–252 行同步调用 `enqueue`，随后不保留该 callback。外层 `task` 不会在 lambda 执行前迭代到下一个值；现有 `test_input_artifact_tasks.py` 也以同步 callback 断言投递参数。该条是当前静态分析误报，不是已证实的错误投递缺陷。
- **边界**：此结论不等于可以忽略所有 lint。`BLE001` 的 8 项盲捕获异常、其余未分类规则，以及 CI 的门禁范围仍需在工程基础设计中明确处理；未修改运行时代码。

## 2026-10-22 — 阶段 1 工程基础：CI/pre-commit 骨架与独立服务验证（进行中）

- **范围**：按 `docs/plans/improvement_and_learning_plan.md` 原计划实施；本轮不修改该计划，保留之前已有的计划与 evidence 工作区修改。新增 `docs/design/engineering_baseline.md`、`.github/workflows/ci.yml`、`.pre-commit-config.yaml`；补充开发工具与贡献说明。没有改业务逻辑、迁移或附件模块。
- **CI**：PR/push/manual 触发，读取仓库的最小权限；Actions 固定到通过 `git ls-remote` 查询确认的提交 SHA。独立执行 Ruff、格式、Pyright、unit/scripts、integration、前端和 Compose 检查；后端以 Python 3.12 为目标，使用 PostgreSQL/pgvector 与 Redis 服务容器，复用初始化 SQL，迁移账号和应用账号分离。错误直接阻断，无 continue-on-error。
- **开发工具**：Ruff `0.16.1`、Pyright `1.1.414`、pre-commit `4.7.0`。本地已安装 hook；首次生成的 Windows 中文解释器路径不是 UTF-8，设置 `PYTHONUTF8=1` 后重新生成，UTF-8 读取后与实际解释器路径完全匹配。贡献指南已补充该设置。
- **配置验证**：actionlint 容器检查最终 workflow，退出 `0`；最初发现 ShellCheck SC2086，已改为 Bash 数组展开，复验通过。`pre_commit validate-config`、`docker compose config --quiet`、`git diff --check` 通过。开发工具声明的 TOML 读取校验通过。
- **真实测试环境**：本轮新建专用 PostgreSQL/Redis 容器，使用动态 loopback 端口，不连接现有开发库；bootstrap 创建角色与 vector 扩展，空库 `alembic upgrade head` 通过。迁移使用 `agent_migrator`，应用测试使用 `agent_app`。
- **后端结果**：本地 Python `3.13.14` 下，`pytest tests/unit tests/scripts -m 'not e2e and not slow' -q` 为 `730 passed, 2 skipped, 2 deselected`，退出 `0`；integration 为 `90 passed, 2 skipped, 5 deselected`，退出 `0`；显式配置独立 Redis 后的合并运行是 `820 passed, 4 skipped, 7 deselected in 47.29s`，退出 `0`。最初未显式接入独立 Redis 的合并运行出现失败后中止，不作为通过证据；未保留完整错误栈，不能断言该次失败的唯一根因。
- **前端结果**：本地 Node `24.16.0` 下 7 项测试和构建通过；另在干净 `node:22-alpine` 容器中只复制前端源码与配置（不复制 .env/node_modules），运行 `npm ci`、`npm test`、`npm run build`，7 项测试及构建通过，最终退出 `0`。
- **仍为红灯**：Ruff 全范围检查 `378` 项，退出 `1`；Pyright 分析 `200` 个文件、`90` 项错误，退出 `1`；格式检查 `108 files would be reformatted, 222 files already formatted`。pre-commit 实际全文件检查退出 `1`，确实阻断这些存量问题，没有自动改写源文件。
- **证据边界**：尚未在 GitHub PR 上运行；本地后端 Python 3.13 结果不能替代 CI Python 3.12 验证；后端依赖尚未完整锁定；本轮没有迁移降级、Worker/外部模型/对象存储 E2E、两项 PR 故障演练、远端必需检查配置，也没有用户独立操作验收。阶段 1 未完成，后续阶段未开始。
- **下一步**：按原计划分批处理静态检查，验证 pre-commit 和 CI 全绿，再推进 PR 审查/故障演练。对 FastAPI 默认参数等报告先判断规则与真实行为，不能为清零直接修改业务契约或整体忽略规则。
- **清理**：确认 `codex.scope=phase1-ci-92d1` 归属后删除本轮两个测试容器及其匿名测试卷；数据可由 bootstrap/迁移/fixture 重建，现有开发容器与数据卷未操作。

## 2026-10-22 — 阶段 1：格式基线与 FastAPI 默认声明规则

- **格式切片**：Ruff 0.16.1 整理 `backend/app`、`backend/tests`、`backend/scripts` 中 108 个 Python 文件，222 个保持原样。没有执行 lint 的批量 `--fix`，没有修改业务契约或开放附件入口。
- **语义核对**：整理前 330 文件的 AST 摘要为 `453bc2ed97ceeeea76d8fa805e2ed0be4da018bfb85c403602c08b79b1e6c6ba`。原始 AST 比较发现 3 个测试文件的 `TypeIgnore.lineno` 随排版移动；逐文件差异只涉及该位置字段。归一化该行号后，与 HEAD 中 330 个原文件的 AST 完全一致，检查退出 `0`。这证明本批未改变解析后的程序结构，不替代完整运行时验收。
- **框架规则**：核对 B008 后，112 项为 FastAPI `Depends`，2 项为 `File`；按 Ruff 官方 `lint.flake8-bugbear.extend-immutable-calls` 精确登记 `fastapi.Depends` 和 `fastapi.File`，没有禁用 B008，也没有调整 API 参数契约。另两项项目自定义默认对象保留待审。依据：https://docs.astral.sh/ruff/settings/#lint_flake8-bugbear_extend-immutable-calls 。
- **防回归**：新增 `tests/scripts/test_ruff_config.py`，四种输入验证框架声明放行、普通工厂默认值拒绝、同名但非 FastAPI 的 `Depends` 拒绝、可变列表默认值拒绝。实跑 `4 passed`，退出 `0`；新测试文件自身 Ruff 检查通过。
- **当前门禁**：`ruff format --check app tests scripts` 为 `331 files already formatted`，退出 `0`；pre-commit 的 ruff-format 全文件检查通过。Ruff 从 378 项降到 251 项（排版消除 13 项，框架精确例外消除 114 项），全量 lint 仍退出 `1`，未宣称 CI 全绿。
- **边界与后续**：本轮没有重跑完整业务测试、没有修复 Pyright、没有推送 PR；上轮 820 项通过是上轮运行证据。下一批审查 import 排序及其模块加载影响，再处理其余规则。原计划未改动，阶段 1 仍未完成。

## 2026-10-22 — 阶段 1：导入排序与隔离回归

- **切片**：仅运行 `ruff check backend/app backend/tests backend/scripts --select I001 --fix`，修复 151 项导入排序报告；没有运行 F401 或行为类规则的批量修复。随后格式检查为 331 个文件已格式化，工作区差异空白检查通过。原计划未修改，附件入口仍冻结。
- **结构核对**：对 HEAD 中 330 个原 Python 文件与当前文件比较 AST，仅归一化连续导入块内的排序、导入语句分组及 `TypeIgnore.lineno`；全部一致，退出 `0`。这说明导入符号和非导入语句结构保留，不代表导入顺序一定没有运行时影响。
- **真实依赖回归**：新建标记 `codex.scope=phase1-imports-a61c` 的 PostgreSQL/pgvector、Redis 与专用网络，loopback 端口分别为 60141、60142；复用 bootstrap SQL，应用账号为 `agent_app`，迁移账号为 `agent_migrator`。显式指定测试数据库和 Redis 后，本地 Python 3.13.14 运行 `pytest tests/unit tests/scripts tests/integration -m 'not e2e and not slow' -q -x --tb=short --durations=3`，结果为 **824 passed, 4 skipped, 7 deselected in 43.77s**，退出 `0`，包含新进程 ORM mapper 启动检查。
- **门禁状态**：Ruff 从 251 项降至 100 项，全范围 lint 仍不通过；未处理 Pyright，未将历史 90 项错误当作本轮重测。没有推送或执行 GitHub PR 检查，没有 Python 3.12 后端运行证据，也未运行 E2E/slow。不得据此宣称阶段 1 完成或用户已经掌握实现。
- **清理**：读取标签确认归属后，删除本轮两个测试容器、其匿名测试卷及专用网络。仅清理可由 bootstrap/迁移/fixture 重建的临时数据，未操作现有开发服务。
- **决定**：保留本批机械整理，继续按规则类别处理剩余 lint 与类型错误；不以关闭检查或改变业务异常契约换取全绿。

## 2026-10-22 — 阶段 1：未使用导入与过期抑制注释

- **范围**：清理 10 项 F401（未使用的 `regex.S`、TaskSpec 模块的标准库/SQLAlchemy 名称、测试中的重复模型导入）及 workflow 模型文件的 8 项 RUF100。保留模型注册所需的实际导入和仍需要的 F401 注释；没有删除模型类、调整字段或开放附件入口。
- **审查依据**：附件上下文的实际实现仍直接导入 `AnalysisTaskInputArtifactVersion`；扫描测试仍导入同一模型模块中的 `ArtifactProcessingJob`；workflow 文件尾部继续注册全部关系目标。源代码搜索未发现外部使用所删除的导入名称。单独选择 F401/RUF100 会将未启用的 BLE001 抑制误报为无用，故没有据此删除其他文件的有效注释，以完整项目规则为准。
- **验证**：全范围 Ruff 剩余 **82 项**，退出 `1`；331 文件格式检查退出 `0`；差异空白检查通过。独立进程导入 TaskSpec，断言表名 `taskspecs` 与唯一列 `id`，退出 `0`。新建独立 PG/Redis，复用 bootstrap 与测试迁移，在 Python 3.13.14 下运行 `pytest tests/unit tests/scripts tests/integration -m 'not e2e and not slow' -q -x --tb=short --durations=3`，**824 passed, 4 skipped, 7 deselected in 39.83s**，退出 `0`，包括新进程 ORM mapper 检查。
- **清理**：确认标签 `codex.scope=phase1-unused-b72d` 后删除本轮测试容器及匿名卷；测试数据可重建，现有开发服务未操作。
- **边界**：未处理剩余 lint/Pyright，未运行 Python 3.12 后端、GitHub PR 或完整 E2E；原计划不变，阶段 1 继续进行，不将机械清理与测试通过等同于用户能力验收。

## 2026-10-22 — 阶段 1：显式字符串拼接分组

- **范围**：`analysis/planner/planning.py` 与 `tests/unit/analysis/test_planning.py` 的 19 项 ISC004。逐项核对后，这些都是有意拼接的完整提示词句子或 JSON 测试响应，而不是遗漏列表逗号。先检查 Ruff 的 diff，再仅对这两个文件启用 ISC004 的修复，添加括号并格式化；未改变提示词内容、列表元素或评测数据。
- **等价性证据**：在同一 Python 进程中保存修改前两个文件的完整 AST，修复后重新解析比较，忽略源码位置属性，两个 AST 完全一致，退出 `0`。这包含全部字符串常量和集合元素，而不只是字符串长度比较。
- **测试**：本地 Python 3.13.14 运行 `pytest tests/unit/analysis/test_planning.py -q --tb=short`，**21 passed in 1.56s**，退出 `0`；显式设置无服务的数据库/Redis 端口，该组测试不需连接数据库或真实模型。全范围 Ruff 剩余 **63 项**，退出 `1`；331 文件格式检查及差异空白检查通过。
- **边界**：本轮只有局部测试与 AST 等价性证据，没有重跑全量回归、真实模型或 E2E；未修复 Pyright，未验证远端 CI。未读取或运行 Gold 留出集。原计划与业务契约不变，阶段 1 未完成。

## 2026-10-22 — 阶段 1：Decimal 整数常量整理

- **范围**：审查修复预览后，仅处理 `reporting/numeric_validation.py` 和 `scripts/data/generate_business_data.py` 的 13 项 FURB157，将整数形式的字符串参数改为整数参数。非整数小数仍保留字符串构造，避免引入二进制浮点误差；不更改金额量化、舍入或数字校验规则。
- **等价性检查**：针对全部 7 种被替换常量，在 Decimal precision 为 1、2、28 时比较 `as_tuple()`，符号、数位、指数一致；修改前后 AST 只将常量 Decimal 调用归一为其精确 tuple，其余完整结构比较一致，退出 `0`。
- **测试与门禁**：Python 3.13.14 下运行 `pytest tests/unit/reporting/test_reviewer_validators.py -q --tb=short`，**17 passed in 0.99s**，退出 `0`。全范围 Ruff 剩余 **50 项**，退出 `1`；331 文件格式检查及差异空白检查通过。
- **边界**：没有执行数据生成脚本、改写经营库、生成评测 fixture 或接触 Gold 内容；没有重跑全量测试、真实模型、Python 3.12 或远端 CI。Pyright 与其余 lint 仍待处理，阶段 1 未完成。

## 2026-10-22 — 阶段 1：引用校验异常传播与清理

- **实现**：删除 `citation_validation.py` 中只原样重抛的 `except Exception: raise`，保留 `finally: db.close()`，不改变权限过滤、查询或失败返回。其余 8 项 BLE001 尚未修改，不能为清零盲目缩窄故障边界。
- **测试**：新增 `test_citation_failure_cleanup.py`，分别注入成员查询、租户范围设置和引用查询异常，断言原异常对象向上传播、会话恰好关闭一次，并确认前置失败不会继续后续查询。与现有 reviewer validator 测试一起执行，首次 20 passed in 1.01s；最终标准命令复验 **20 passed in 0.99s**，退出 `0`。使用 Mock，不是 PostgreSQL 故障演练或完整权限证据。
- **辅助验证未完成**：另尝试在独立进程内移除清理逻辑并调用 `pytest.main`，两次均未返回测试结果后主动中止；没有获取根因栈，不将其视为测试通过、预期失败或已知环境故障。内存变异未写入源码，随后标准 pytest 命令复验通过。
- **门禁**：全范围 Ruff 剩余 **49 项**，退出 `1`；332 文件格式检查通过。Pyright、全量回归、Python 3.12、远端 CI 尚未在本轮验证，阶段 1 未完成。

## 2026-10-22 — 阶段 1：类型导入与声明整理

- **修改**：3 处 Callable 改用 `collections.abc`；已启用 postponed annotations 的 SnapshotCatalog 移除多余返回类型引号；UTF-8 测试断言使用默认 encode；currency 类型声明去除 float 已覆盖的 int。只处理预览确认的 6 项 UP035/UP012/UP037/PYI041，并重新整理受影响导入顺序。不改变附件入口或解析流程。
- **保留待处理**：OCR 回调仍声明返回 object，两个 B009 不直接修复，避免把运行时属性访问替换后留下新的静态类型错误；后续需与真实 OCR 返回契约一起审查。
- **验证**：Python 3.13.14 下运行 image_ocr、pdf_render、parser、snapshot_catalog_validator 四个单元测试文件，**25 passed in 0.99s**，退出 `0`。单独从 AST 加载 currency 函数，验证 None、零、整数、浮点数、Decimal 五种输入输出，全部通过；没有运行数据生成脚本或操作数据库。
- **门禁与边界**：全范围 Ruff 剩余 **43 项**，退出 `1`；332 文件格式检查和差异空白检查通过。没有重跑完整回归、真实 OCR 服务、Python 3.12 后端、Pyright 或远端 CI；阶段 1 未完成。

## 2026-10-23 — 阶段 1：测试状态隔离与冻结默认对象

- **测试隔离**：模型预算测试的 Task 替身原先将三个可变字典放在类属性上。新增两个实例不共享字典（包含嵌套 calls_by_node）的断言，旧实现明确失败；改成构造函数内逐实例初始化后，预算测试 11 项通过。这证明替身的共享状态风险已修复，不代表生产任务曾经发生串扰。
- **默认对象**：parse_worker 的两项 B008 对应仅含数值字段的 frozen dataclass，沿用 parser 的模块常量模式，保留原默认值和共享不可变对象语义。新增两项测试核对默认值并验证修改属性触发 FrozenInstanceError；未改附件入口或解析业务流程。
- **验证**：最终显式选择预算测试、parser 测试以及 worker 默认对象测试，**30 passed in 1.42s**，退出 `0`。首次用不匹配的排除表达式选择测试，误包含需数据库的 worker 测试，在无服务端口上未完成后中止；这次运行不算通过证据，随后使用精确测试节点重新验证。
- **门禁与边界**：全范围 Ruff 从 43 项降到 **38 项**，退出 `1`；未重跑真实数据库 worker 测试、完整回归、Pyright、Python 3.12 或远端 CI。原计划不变，阶段 1 未完成。

## 2026-10-23 — 阶段 1：上下文管理与条件简化回归

- **范围**：合并 schema discovery、文本文件复制与测试中的 5 处嵌套 with，保持进入顺序及逆序退出；合并格式校验的两处嵌套条件，保持短路顺序；将未使用的测试局部变量命名为 `_context`。没有调整循环编号、SQL 字符串或异常契约。
- **等价性**：从 HEAD 和当前文件分别加载 `validate_schema`，对 8 类文本、4 类证据数量和两种引用要求组成的 64 个输入组合逐个比较，结果完全一致，退出 `0`。
- **真实服务回归**：使用本轮独立 PostgreSQL/pgvector 与 Redis（loopback 60141/60142），bootstrap 初始化角色与空库，应用测试使用 agent_app，迁移使用 agent_migrator。Python 3.13.14 执行 `pytest tests/unit tests/scripts tests/integration -m 'not e2e and not slow' -q -x --tb=short --durations=3`，**830 passed, 4 skipped, 7 deselected in 41.47s**，退出 `0`，覆盖前几轮新增测试及解析 Worker 数据库测试。
- **门禁**：全范围 Ruff 剩余 **30 项**，退出 `1`；332 文件格式检查及差异空白检查通过。尚未运行 Python 3.12 后端、Pyright 新结果、真实外部模型/完整 E2E 或 GitHub PR；阶段 1 未完成。
- **清理**：核对 `codex.scope=phase1-contexts-c83e` 后删除本轮两个测试容器及匿名卷；仅清理可重建临时测试数据，没有操作现有开发服务。

## 2026-10-23 — 阶段 1：OCR 返回类型与 Pyright 复核

- **契约**：复用现有 ImageOcrResult，补齐 parse_worker → parser → 图片/PDF OCR 提取链的 Callable 返回类型，并将两个常量 getattr 改为直接属性访问。实际 Tesseract 适配器与测试替身均返回该类型；没有新增抽象、移除字段校验或改变异常处理，附件入口保持冻结。
- **测试**：image_ocr、parser、input_artifact_tasks 与 worker 默认值测试共 **23 passed in 0.70s**，退出 `0`。这是适配器/解析单元证据，不是实际 Tesseract 服务或 Worker 数据库 E2E。
- **类型检查**：第一次在 backend 目录引用不存在的 pyrightconfig.json，提示配置不可读并错误扩大分析范围，其 495 项结果不作为项目基线。按仓库根目录真实配置重跑，修改前后均为 **200 文件、90 项错误**，Pyright 退出 `1`；修改后的 parser、parse_worker、image_ocr 无诊断。CI 的 Pyright 步骤本来就在仓库根目录，未作无必要修改。
- **门禁与边界**：Ruff 剩余 **28 项**，退出 `1`；332 文件格式检查及差异空白检查通过。没有重跑全量回归、Python 3.12 后端或远端 CI；类型错误总量尚未下降，阶段 1 未完成。

## 2026-10-23 — 阶段 1：SQL 生成参数类型契约

- **根因与修改**：DataAgent 临时 kwargs 字典先从 repair_reason/previous_sql 推断为字符串或 None，之后插入 required_concepts 列表和 evaluation_scope 字典，引发 4 项类型错误。删除该临时字典，直接向 SQLGenerationService.generate 的既有关键字参数传值；空业务能力列表仍按原语义使用 None。没有加 Any、cast 或忽略注释，没有修改 SQL 执行、权限或重试策略。
- **验证**：生产生成器与测试替身的四个可选参数均以 None 为默认值。运行 `test_agents.py` 与 `test_sql_generation.py`，**55 passed in 1.18s**，退出 `0`，覆盖修复重试、能力要求与 planner 范围传递。修改文件 Ruff 通过，全范围 332 文件格式检查和差异空白检查通过。
- **类型门禁**：按根目录配置执行 Pyright 1.1.414，分析 200 个文件，错误从 90 降至 **86 项**，退出 `1`；data_agent.py 无剩余诊断。全量 Ruff 上轮仍有 28 项，本轮未宣称全绿。
- **边界**：本轮仅单元/契约与静态验证，没有真实模型、数据库 SQL 全链、Python 3.12 运行或远端 CI 证据。原计划不变，阶段 1 未完成。

## 2026-10-23 — 阶段 1：模型成本的 Decimal 注解

- **依据与修改**：ModelCallRecord 的 cost/reserved_cost 均显式映射 Numeric(12, 6)，迁移也声明相同类型；预算预留与结算代码使用 Decimal，但 ORM 注解误写成 float。将两列注解更正为 Decimal | None，不改列类型、可空性、数据库内容或计算逻辑，不通过 float 转换消除类型错误。
- **验证**：现有付费调用测试新增 Decimal 实例与精确预留金额断言。`test_model_governance.py` **11 passed in 0.59s**，退出 `0`；修改文件 Ruff、全范围 332 文件格式检查及差异空白检查通过。按根目录配置运行 Pyright，200 文件，错误从 86 降至 **85 项**，退出 `1`，model_governance.py/model_call.py 无诊断。
- **边界**：本轮 FakeDb 测试证明预留和结算对象的类型及金额，不证明数据库往返精度或供应商计费正确；未运行真实 PostgreSQL 往返、Python 3.12 或远端 CI。阶段 1 未完成。

## 2026-10-23 — 阶段 1：确定性评测三态类型契约

- **修改**：为既有状态字典和列表明确 CheckStatus 类型；RequiredTerms 参数使用其真实列表类型；将结果构造中的混合字典展开替换为具名字段。拒绝/澄清分支中原本确定为布尔值的 outcome/budget/route 字段从规范化状态转换回布尔值，硬门禁、violations 与 unknown_checks 算法不变。SQL 行数上限使用已有 Pydantic 验证器保证的非空约束；费用汇总显式识别缺失金额并沿用 unknown 分支，不把缺失值补零。
- **测试范围更正**：最初计划运行不读取 fixture 的测试，但 `-k 'not fixture'` 按名称筛选仍包含读取命名开发集的测试；后续 AST 检查确认这些为开发集测试，Gold 两项测试被排除，未读取 Gold 文件内容或运行其评测。不得将这次结果称为纯内存测试或独立留出集证据。
- **验证**：新增缺失金额却标记 passed 的回归测试，确认 settled_cost 为 None、cost_status 为 unknown。最终 `pytest tests/unit/evaluation/test_business_evaluation.py -k 'not fixture' -q --tb=short` 为 **56 passed, 6 deselected in 0.17s**，退出 `0`；修改文件 Ruff、全范围 332 文件格式检查与差异空白检查通过。
- **类型结果**：根目录 Pyright 配置分析 200 文件，错误从 **85 降至 32 项**，退出 `1`；business.py 无剩余诊断。没有添加 Any、cast 或类型忽略，也没有降低业务硬门禁或调整评测阈值。
- **边界**：本轮依 evaluation 技能保持确定性门禁与开发/留出隔离；不构成真实 Agent 质量提升或阶段 2 评测基线完成。未跑全量回归、Python 3.12 或远端 CI，阶段 1 仍未完成。

## 2026-10-23 — 阶段 1：工作流阶段回调签名

- **调用链**：Worker 传入接受 stage/node_name 的回调；run_analysis 将其放入 WorkflowState；节点 `_set_stage` 实际调用 `callback(stage, node_name)`。WorkflowState 已声明两参数，只有 run_analysis 的注解错误写成一参数。修正为 Callable[[str, str], None]，不改变运行逻辑、Worker 兼容参数或阶段更新行为。
- **验证**：扩展现有编译图终态测试，使用必须接受两个参数的回调，断言实际收到 `(planning, planner_node)`。`test_workflow.py` **32 passed in 2.54s**，退出 `0`；修改文件 Ruff、332 文件格式检查及差异空白检查通过。根目录 Pyright 分析 200 文件，错误从 32 降至 **31 项**，退出 `1`，graph.py 无诊断。
- **边界**：本轮使用编译后的真实图和 FakePlanner，未调用外部模型或验证数据库阶段持久化；未跑完整回归、Python 3.12 或远端 CI，阶段 1 未完成。

## 2026-10-23 — 阶段 1：SQL 查询与结果结构类型约束

- **实现**：行数限制函数复用现有 `_parse_single_select`，明确得到 Select AST，而不是从任意 Expression 强行调用 limit；正常执行入口仍先调用完整 validate_sql。结果校验在已有非空和行结构验证后，明确首行的 list/tuple 类型再检查空聚合。不添加 Any/cast，不放宽允许表或结果形状。
- **验证**：新增非 SELECT/多语句的行数限制拒绝测试，以及 6 种畸形结果行的拒绝测试。查询结果、SQL executor、SQL validator 与 DataAgent 测试合计 **75 passed, 2 skipped in 1.55s**，退出 `0`；两项需要经营数据库的既有测试仍跳过。修改文件 Ruff、332 文件格式检查与差异空白检查通过。
- **类型门禁**：Pyright 200 文件，错误从 31 降至 **29 项**，退出 `1`；query_validation.py/sql_executor.py 无诊断。
- **边界**：本轮未连接经营数据库、未验证真实 SQL 端到端、Python 3.12 或远端 CI；阶段 1 未完成。

## 2026-10-23 — 阶段 1：对象存储健康检查的配置类型收窄

- **实现**：健康检查将 all(tuple) 改为等价的逐项缺失判断，使类型检查能确认访问凭据前配置存在。保留缺项返回 not_configured、服务错误返回 unavailable、超时与重试配置；没有输出密钥、修改 Settings 或改变实际连接参数。对象存储上传/处理适配器的剩余类型问题尚未修改。
- **验证**：新增 endpoint、bucket、access key、secret key 四类缺项测试，断言不创建 S3 客户端。`test_health_repository.py` **6 passed in 0.20s**，退出 `0`；修改文件 Ruff、332 文件格式检查及差异空白检查通过。Pyright 分析 200 文件，错误从 29 降至 **27 项**，退出 `1`。
- **边界**：这些为 Mock 客户端测试，未验证真实对象存储、服务故障或远端 CI；未跑完整回归和 Python 3.12。阶段 1 未完成。

## 2026-10-23 — 阶段 1：持久化观察记录的类型与未知状态

- **修改**：SQLAlchemy Row 通过显式二元解包构造文档/块映射；终态字典使用 Outcome，澄清槽位沿用 ClarificationSlot。数据状态先检查字符串类型，避免列表/字典进入集合查找时报错；确定性校验仅显式 passed/failed 转为对应状态，其余保持 unknown。未填造缺失文档路径或更改租户过滤。
- **验证**：新增 6 种非法状态和 4 种合法状态测试；在独立 PostgreSQL/pgvector 上初始化角色、迁移测试库，运行 `test_observation.py`，**30 passed in 1.88s**，退出 `0`。使用 agent_app 与 agent_migrator 分离账号；不是 Mock 数据库。修改文件 Ruff、332 文件格式检查及差异空白检查通过。
- **类型结果**：Pyright 分析 200 文件，错误从 27 降至 **16 项**，退出 `1`，observation.py 无诊断。
- **清理与边界**：核对 `codex.scope=phase1-observation-d94f` 后删除专用测试容器及匿名卷，临时数据可重建，现有开发服务未操作。未运行 Gold、真实模型、全量回归、Python 3.12 或远端 CI，阶段 1 未完成。

## 2026-10-23 — 阶段 1：MCP 已验证上下文的类型收窄

- **实现**：既有 `_is_valid_runtime_context` 已检查字典、固定字段、角色与范围指纹。将输入注解收紧为 object，返回注解改为 TypeGuard[dict[str, Any]]，让调用方识别通过验证后的字典类型；函数体、授权检查和指纹逻辑均未改动，没有用 cast 绕过验证。
- **验证**：`test_mcp_adapter.py` **11 passed in 2.93s**，退出 `0`，覆盖缺失上下文拒绝、回执不匹配、目录/返回契约及断开 stdio 等现有场景。修改文件 Ruff、332 文件格式检查与差异空白检查通过。Pyright 200 文件，错误从 16 降至 **14 项**，退出 `1`。
- **边界**：使用现有测试 reader 与本地传输，不证明真实 RAG 检索权限端到端；未跑全量回归、Python 3.12 或远端 CI，阶段 1 未完成。

## 2026-10-23 — 阶段 1：报告引用文本类型收窄

- **实现**：限定条件逐字核对所用的 chunk→content 映射复用 isinstance 检查过的局部值，声明为 dict[int, str]，不重复读取可能被推断为 None 的 get 返回值。保留原有授权 chunk 子集检查、逐字匹配与不匹配丢弃规则。
- **验证**：新增 None、数字、字典、列表及不匹配文本的拒绝测试。`test_reviewer_validators.py` **22 passed in 1.24s**，退出 `0`；修改文件 Ruff、格式整理后的 332 文件格式检查通过。Pyright 200 文件，错误从 14 降至 **13 项**，退出 `1`。
- **边界**：本轮没有真实文档检索或模型语义审核，没有全量回归、Python 3.12 或远端 CI 证据；阶段 1 未完成。

## 2026-10-23 — 阶段 1：对象存储适配器凭据收窄

- **实现**：处理存储客户端、直传签名和对象检查在创建 S3 客户端前，检查局部凭据是否为 None；缺项沿用存储不可用异常，阻止回退到默认凭据链。保留构造时完整配置校验及公网/内网 endpoint 路由，未开放冻结的上传入口。
- **验证**：新增 6 个凭据在初始化后缺失的场景，断言不创建客户端。两个存储测试文件共 **12 passed in 0.14s**，退出 0。Pyright 分析 200 文件，错误由 13 降至 **7 项**，退出 1；本次修改文件 Ruff 通过。整理新测试格式后，按 CI 范围 app/tests/scripts 检查格式通过。
- **范围说明**：额外尝试对整个 backend 检查格式发现迁移文件等范围外格式债务，不等同于当前 CI 范围失败；未修改这些文件。本轮为 Mock 测试，未验证真实对象存储、全量回归、Python 3.12 或远端 CI，阶段 1 未完成。

## 2026-10-23 — 阶段 1：上传回执的状态契约校验

- **实现**：三个回执构造函数使用现有 Pydantic model_validate 校验显式字段字典，解决数据库 str 与响应 Literal 状态类型不匹配的五项诊断；未使用 cast、忽略诊断或放宽状态集合。原有公司校验、租户限定版本查询及缺失版本异常保持不变，未开放上传入口。
- **验证**：新增三个构造路径的合法/非法状态及两条路径的非法版本状态测试，共 8 个场景。先运行无数据库契约子集，13 passed、10 deselected；再启动独立 PostgreSQL/pgvector，初始化角色并迁移测试库，完整运行 test_api.py 与 test_schemas.py，**23 passed in 2.57s**，退出 0。修改文件 Ruff、CI 范围 332 文件格式检查及差异空白检查通过。
- **静态状态**：Pyright 分析 200 文件，错误由 7 降至 **2 项**，退出 1；剩余为评测阈值与 Worker 公司范围的可空类型，尚未修改。
- **清理与边界**：确认 scope 标签后删除 codex-phase1-api-7a21 测试容器及匿名卷，临时数据可重建；未操作现有开发服务。数据库为真实独立 PG，对象存储仍为测试替身；未验证全量回归、Python 3.12 或远端 CI，阶段 1 未完成。

## 2026-10-23 — 阶段 1：成本比较倍率缺失时拒绝

- **实现**：相对成本比较在乘法之前明确检查倍率为 None，与已有耗时倍率检查保持一致。正常构造仍由 Pydantic 要求基线 hash 与两种倍率齐备；若对象被未校验的 model_copy 修改，不再以 TypeError 中断，而返回 cost_per_trusted_success_multiplier 违规项，不可判定通过。
- **验证**：先添加成功数非零、倍率缺失的回归断言，运行得到 1 failed、7 passed，失败原因为 Decimal 乘 None；修复后同一测试文件 **8 passed in 0.08s**，退出 0。修改文件 Ruff 与 CI 范围 332 文件格式检查通过。仅使用现有开发数据，未读取 Gold 留出集。
- **未证明**：未跑全量回归、Python 3.12 或远端 CI。本轮未修改 Worker；其 company_id 可空是历史任务的显式兼容行为，需要在附件范围边界处理，不能直接强制转换为 int。阶段 1 未完成。

## 2026-10-23 — 阶段 1：历史任务与附件公司范围契约

- **实现**：build_task_attachment_context 显式接受 int | None。无冻结附件时维持空上下文；有冻结附件但 company_id 缺失时，在内容查询前抛出 attachment_company_scope_missing。未给历史任务补造公司，也未放宽租户过滤。原实现已通过无法匹配附件拒绝这一情况，本轮不是修复已证实的数据泄露，而是明确输入与失败契约。
- **验证**：新增无公司且无附件、已有附件但传入空公司范围两个场景。修复前 3 passed、1 failed，失败为预期专用错误码与原笼统错误码不符；修复后独立 PostgreSQL/pgvector 上运行附件上下文和 Worker 终态测试，**15 passed in 2.27s**，退出 0。存储替身被禁止读取，证明缺少范围时未调用对象下载。
- **静态结果**：Pyright 使用本地 Python 3.13 环境分析 200 文件，**0 errors / 0 warnings**，退出 0；修改文件 Ruff、332 文件格式检查通过。全 CI 范围 Ruff 仍 **28 项**，退出 1，不能宣称静态门禁全部通过。
- **清理与边界**：核对 scope 后删除 codex-phase1-scope-18bf 专用容器和匿名卷，临时测试数据可重建。未跑全量回归、Python 3.12 或远端 CI，未证明用户独立实现能力，阶段 1 未完成。

## 2026-10-23 — 阶段 1：Outbox 回调绑定与测试类型注解

- **实现**：附件 Outbox 每次迭代创建的 enqueue 回调通过默认参数绑定当次 Celery task，避免延迟调用读取循环最后一个 task；原有公司、job、dispatch_generation 传参保持不变。Schema discovery 的两个测试上下文管理器返回注解改为 Self，运行逻辑不变。
- **验证**：新增混合 scan/parse 事件、循环结束后分别调用回调的测试；修复前 1 failed、2 passed，scan 被错投到 parse；修复后加上 schema discovery 测试 **4 passed in 0.09s**，退出 0。当前生产发布函数同步执行回调，所以测试证明的是闭包绑定问题，不是已发生的生产错投。
- **门禁**：Ruff 从 28 降至 **25 项**，退出 1；修改文件 Ruff 与 332 文件格式检查通过。本轮未跑真实 Broker、全量回归、Python 3.12 或远端 CI，阶段 1 未完成。

## 2026-10-23 — 阶段 1：合成数据编号循环整理

- **实现**：采购/运营生成函数复用 enumerate 的 ticket_id，月度文档使用从 1 开始的 enumerate；移除两个冗余自增计数器。没有改随机种子、随机调用顺序、编号起点或数据内容，SQL 校验脚本本轮未改。
- **验证**：修改前后用 Mock cursor 执行 seed_dimensions 与 seed_transactions（后者调用采购/运营生成），捕获完整 22 批数据库调用。两次 repr(mock_calls) 的 SHA-256 均为 `06a74c243b0e83e84eeca48753908985bd8b91280d66b5b1f66b4588f18f5e1c`。第一次修改后执行发现遗漏 index 引用导致 NameError，补齐后重跑成功，退出 0。没有执行 main、recreate_schema、真实数据库写入或语料文件生成。
- **门禁与边界**：修改文件 Ruff 通过，CI 范围 332 文件格式通过；全范围 Ruff 剩 **23 项**，退出 1。该验证只证明固定种子下生成调用内容一致，不证明真实数据库导入或业务正确；未跑全量回归、Python 3.12、远端 CI，阶段 1 未完成。

## 2026-10-23 — 阶段 1：SQL 与快照值校验的规则例外

- **判断依据**：SQL 非 SELECT 检查处理的是 SQL 字符串内容，不是调用参数类型；SQLTool 捕获 ValueError 返回 sql_validation_error 可修复回执。快照检查处理持久化 JSON 内容不合法，沿用统一 ValueError 契约。机械替换为 TypeError 会改变既有失败语义。
- **实现**：保留运行代码，仅在上述 5 个抛出点添加有原因说明的 TRY004 行级例外，没有全局关闭规则。新增 6 类非法快照内容的契约测试。
- **验证**：test_snapshot_catalog_validator.py、test_sql_validator.py、test_tools.py **37 passed in 0.19s**，退出 0。全范围 Ruff 剩 **18 项**，退出 1；332 文件格式检查通过。未新增真实数据库或模型验证，未跑全量回归、Python 3.12 或远端 CI；阶段 1 未完成。

## 2026-10-23 — 阶段 1：Outbox 失败记录不持久化异常正文

- **发现与实现**：分析任务发布失败原先把异常类型及完整异常正文写入 last_error，可能保存连接凭据。改为固定 broker_publish_failed；保留日志中事件 ID、任务 ID、异常类型，不记录正文。保留失败恢复 pending 的通用异常边界，为该处 BLE001 添加行级理由。未清理或读取既有业务失败记录。
- **验证**：使用虚构含凭据 URL 的 ConnectionError，修复前实际持久化了测试异常正文；修复后断言固定错误码、日志记录存在且包含定位字段、不含测试密码，并继续验证成功重投、Worker 认领与其他租约/取消场景。迁移配置禁用 logger 导致第一次日志断言未捕获记录，测试显式恢复目标 logger 后重跑。独立 PostgreSQL 上 **4 passed in 0.41s**，退出 0。
- **门禁与边界**：全范围 Ruff 剩 **17 项**，退出 1；332 文件格式通过。核对 scope 后删除 codex-outbox-redact-91ac 测试容器和匿名卷，临时数据可重建；未验证真实 Broker、全量回归、Python 3.12 或远端 CI，历史失败记录是否含敏感信息未检查。阶段 1 未完成。

## 2026-10-23 — 阶段 1：工具失败回执边界

- **判断与实现**：SQLTool、TemplateQueryTool、ToolRuntime 的通用异常捕获用于转换未知依赖错误为明确失败，并隔离异常正文。保留行为，为三处 BLE001 添加局部原因说明，没有扩大捕获范围或记录原始异常。
- **验证**：查询工具测试 **19 passed in 0.16s**；加强 Runtime 测试，检查加载的事件/工具记录字段及 dataclass 回执不含虚构私密异常正文或请求正文，而不是仅检查 ORM 默认 repr。首次测试误把 ToolOutput 当成 Pydantic 模型调用 model_dump_json，核对其 dataclass 定义后修正；独立 PostgreSQL 上完整 Runtime 测试 **18 passed in 1.52s**，退出 0。
- **门禁与边界**：Ruff 剩 **14 项**，退出 1；332 文件格式通过。核对 scope 后删除 codex-tool-boundary-3a8c 专用容器和匿名卷，测试数据可重建。工具依赖为替身，未证明真实业务库/模型端到端、全量回归、Python 3.12 或远端 CI，阶段 1 未完成。

## 2026-10-23 — 阶段 1：附件异常契约与剩余机械整理

- **实现**：为已核对的租户 Session 状态错误、元数据拒绝、未知处理失败的恢复/清理边界添加逐行 TRY004/BLE001 例外说明，未更换异常类型或修改恢复逻辑；API 仍按 ValueError 拒绝非法输入。长规划提示词保留逐行 join 的可审阅结构并说明 FLY002 例外；RAG 充分性布尔返回简化为等价的 not-less-than，未改变阈值或非有限值行为。
- **验证**：独立 PostgreSQL/pgvector 上附件单元目录及分析 Outbox 共 **182 passed in 7.67s**；RAG 与重排测试 **8 passed in 0.04s**，均退出 0。第一次 RAG 命令末尾误附不存在命令使 shell 退出 1，去掉后重新运行确认退出 0，未据第一次 shell 状态宣称通过。
- **静态结果**：异常契约整理后 Pyright 200 文件 **0 errors / 0 warnings**，退出 0。最终 Ruff 剩 **1 项**，为数据校验脚本 SQL 字符串插值；332 文件格式通过。没有关闭全局规则。
- **清理与边界**：核对 scope 后删除 codex-artifact-regression-4f9b 专用容器与匿名卷，可重建测试数据；未开放冻结入口。未验证全量回归、Python 3.12、远端 CI 或真实对象存储，阶段 1 未完成。

## 2026-10-23 — 阶段 1：本地静态门禁通过与广泛回归

- **实现**：数据校验脚本 scalar 接收可选参数元组，月度日期通过 psycopg 参数传递而不拼接 SQL；现有无参数调用传 None。新增脚本级测试覆盖有参数与无参数路径，不调用脚本 main 或真实业务库。
- **静态验证**：`ruff check backend/app backend/tests backend/scripts` 退出 **0**；对应格式检查 **333 files already formatted**，退出 **0**；Pyright 使用本地 Python 3.13 分析 **200 文件、0 errors / 0 warnings**，退出 **0**。脚本参数与 Ruff 配置测试 **6 passed in 0.61s**。
- **广泛回归**：独立 PostgreSQL/pgvector 与 Redis 初始化后执行 `pytest tests/unit tests/scripts tests/integration -m 'not e2e and not slow' -k 'not business_gold' -q --tb=short`，**881 passed, 4 skipped, 9 deselected in 45.45s**。这是明确排除范围的本地回归，不是所有测试或完整业务端到端；没有用 Gold 结果调参或宣称独立留出晋升。
- **清理与未证明**：核对 full-6c12 标签后移除 codex-full-pg-6c12、codex-full-redis-6c12 及匿名卷，临时测试数据可重建。未验证 Python 3.12 干净安装、GitHub CI/PR 拦截与回退演练、真实模型/对象存储或用户独立能力；阶段 1 仍未完成。

## 2026-10-23 — 阶段 1：Python 3.12 干净容器验证

- **环境**：python:3.12-slim，实际 Python 3.12.15；选择性复制代码、测试、配置，不复制 .env 或已有虚拟环境。按 CI 命令安装 base.txt 与 backend[dev] 成功，pip check 无依赖冲突。依赖仍为范围解析，尚非完整锁定。
- **发现与修复**：首次测试收集失败，缺少 PIL；将已在 ml.txt 使用的 Pillow==12.3.0 加入 dev 依赖，重新执行安装成功。Windows docker cp 为普通源码附带执行权限导致 EXE002；将临时副本恢复为普通文件权限后，另发现 3 个 Git 模式 100644 文件含 shebang，移除这些非可执行 Python 文件的不适用头部。没有禁用 Linux 权限规则。
- **验证**：独立 Docker 网络的 PostgreSQL/pgvector 与 Redis 上，`pytest tests/unit tests/integration -m 'not e2e and not slow' -k 'not business_gold'` 得到 **852 passed, 4 skipped, 9 deselected in 26.41s**，退出 0。修正权限及头部后容器 Ruff 检查通过，333 文件格式通过，pip check 通过。此结果不含 tests/scripts，也未验证容器 Pyright，不能等同完整 CI 通过。
- **续作资源**：保留专用容器 codex-clean312-8e2a、codex-clean312-pg-8e2a、codex-clean312-redis-8e2a 与网络 codex-clean312-net-8e2a，均标记 scope=clean312-8e2a，供后续脚本与类型验证，尚未清理。没有改动开发服务。远端 CI/PR 故障演练与学习验收未完成，阶段 1 未完成。

## 2026-10-24 — 阶段 1：Python 3.12 脚本与类型验证补齐

- **环境诊断**：初跑 tests/scripts 为 5 failed、24 passed，缺 pwsh 与仓库根目录 scripts 副本。补齐根 scripts，按微软 Debian 官方文档安装 PowerShell 7.6.8 后，**29 passed in 2.98s**，退出 0；不通过 skip 隐藏缺项。官方安装依据：https://learn.microsoft.com/en-us/powershell/scripting/install/install-debian 。
- **类型诊断**：首次 Pyright 的 Node 自动安装遇到下载不完整及 libatomic.so.1 缺失，退出 1，未执行类型分析；确认该进程终止后使用系统 Node 20.19.2 重跑。Python 3.12 当前解析出的 SQLAlchemy 2.1.6 将 COALESCE 结果仍推断可空，产生一项成本类型诊断。查询保证非空，因此补充 assert 明确不变量，没有 cast 或 Python 端填造成本。
- **验证**：真实独立 PG 上指标汇总空公司与有费用公司测试 **2 passed in 0.13s**，退出 0；随后容器 Pyright **0 errors / 0 warnings**、退出 0（配置提示缺少 .venv，但已显式指定系统解释器）；Ruff 通过，333 文件格式通过。此前 852 项单元/集成结果与本轮脚本结果为分别运行，不声称同一轮全套测试。
- **清理与边界**：确认 scope 后移除 clean312-8e2a 的三个专用容器、匿名卷及专用网络，临时环境可重建；主机开发依赖和业务服务未修改。仍未完成依赖精确锁定、远端 CI、PR 故障/回退演练及学习验收，阶段 1 未完成。

## 2026-10-24 — 阶段 1：CI 依赖锁生成中（未采用）

- **范围**：首先为 Linux/Python 3.12 CI 生成锁，输入为 pyproject.toml 的 dev 及运行依赖、requirements/base.txt 和构建依赖；不将 Windows 环境或 ML Worker 混入此锁，不宣称全项目依赖已经锁定。
- **环境与命令**：专用 python:3.12-slim 容器 codex-lock312-b41e，scope=lock312-b41e；已安装 pip==26.2.2、pip-tools==7.6.2。工具拒绝在多输入时使用 --all-build-deps，故先用 `python -m piptools compile --all-build-deps --only-build-deps --allow-unsafe --strip-extras --no-emit-index-url --no-emit-trusted-host --quiet --output-file /tmp/ci-build.txt pyproject.toml` 提取构建依赖，已退出 0。
- **进行中**：工作目录 /workspace/backend，随后运行 `python -m piptools compile --extra dev --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url --no-emit-trusted-host --quiet --output-file requirements/ci-linux-py312.lock pyproject.toml requirements/base.txt /tmp/ci-build.txt`；最后检查进程仍活跃，尚无退出码或最终锁文件。此条是待续检查点，不是完成证据；后续须确认该进程实际终态，不能仅按记录重启。
- **未采用**：宿主仓库尚未添加锁文件，也未修改 CI 安装入口；须验证生成结果、哈希安装与测试后再采用。容器暂留，阶段 1 未完成。

### 同日续查：依赖锁生成等待与安装文档对齐

- 已复查原 pip-compile 进程仍活跃，缓存从约 295 MB 增长至 330 MB，最终锁文件尚未出现；没有启动第二个生成进程，也没有把等待视为失败或通过。
- CONTRIBUTING 的本地安装补上 requirements/base.txt，与 CI 的双输入安装一致；静态检查命令补上 scripts。记录已验证可启动的两步锁生成命令、独立环境要求及未采用边界。文档差异空白检查通过，实际哈希安装与锁采用仍待生成完成。

## 2026-10-24 — 阶段 1：CI 依赖锁本地验证与接入

- **生成终态**：原 pip-compile 进程退出 0，生成 117 个精确版本包及 SHA-256 哈希；已添加 `backend/requirements/ci-linux-py312.lock`。生成期间一次 PyPI 读取超时自动重试后成功，没有重启生成任务或手填锁内容。
- **隔离安装**：在专用 Linux x86_64/Python 3.12.15 容器新建 `/opt/ci-verify` 虚拟环境；`pip install --require-hashes -r requirements/ci-linux-py312.lock` 退出 0。随后 `pip install --no-index --no-build-isolation -r requirements/base.txt -e '.[dev]'` 与 `pip check` 均退出 0；验证项目及原依赖声明可在锁定实装集合上离线满足，不继承生成器环境。
- **回归**：专用网络内 PostgreSQL/pgvector 与 Redis，应用账号执行 `pytest tests/unit tests/scripts tests/integration -m 'not e2e and not slow' -k 'not business_gold' -q --tb=short`，**882 passed, 4 skipped, 9 deselected in 32.97s**，退出 0。未读取或使用冻结 Gold 调参；跳过、排除不算通过。
- **静态检查**：锁定环境 Ruff 检查通过、333 文件格式通过；Pyright 显式指定该虚拟环境，**0 errors / 0 warnings / 0 informations**，退出 0。系统 Node 20.19.2 和 PowerShell 7.6.8 仅用于验证所需工具，不属于 Python 锁内容。
- **接入**：CI 的 static/backend 两处安装均切换为哈希安装、离线项目安装、pip check；更新 CONTRIBUTING 与工程基础设计，不修改原计划。修改后 actionlint 退出 0，git diff --check 退出 0（有现有 LF/CRLF 提示）。远端工作流仍未执行，不能将本地结果称为 GitHub CI 全绿。
- **清理与边界**：确认 scope=lock312-b41e 后删除三个专用容器、匿名卷与专用网络；生成器缓存与临时测试数据已清理，可重新生成，仓库锁文件保留。本锁不涵盖 ML Worker、Windows 或系统镜像；迁移回滚、PR 故障演练、分支保护及用户独立操作仍未验收，阶段 1 未完成。

## 2026-10-24 — 阶段 1：最新迁移往返与不兼容数据故障演练

- **隔离环境**：新建 `codex-migration-pg-7c2a`（scope=migration-7c2a），pgvector 0.8.0 / PG16，仅映射随机本机端口 61133。复用 bootstrap SQL，显式指定 agent_platform_test 与迁移角色 agent_migrator；本机 Python 3.13 执行 Alembic，不连接开发数据库。未改迁移实现。
- **空库路径**：`alembic upgrade head` 从空库升级至 x1a2b3c4d5e6，退出 0；`alembic downgrade -1` 回到 w0a1b2c3d4e5、再 upgrade head，分别退出 0。
- **故障注入**：以迁移角色加入独立合成用户/会话/消息（ID 900001），消息状态 awaiting_review。随后 downgrade -1 退出 **1**，明确报 ck_conversation_messages_status_values CheckViolation。SQL 复核版本仍为 x1a2b3c4d5e6、原检查约束仍允许 awaiting_review、该消息正文及状态完整；证明本场景事务回滚，没有半迁移或丢失该测试记录。
- **兼容数据路径**：仅将专用库里的合成消息置为 completed，作为另一个测试前提，不是业务修复建议。downgrade -1 与 upgrade head 再次均退出 0；复核版本与合成消息 ID、正文、completed 状态保持。CONTRIBUTING 补充停止写入、备份、检查不兼容状态与禁止伪造完成状态的操作边界。
- **未证明范围**：仅验证最新一跳；没有证明全链 downgrade、真实业务数据回退、备份恢复、Python 3.12 下该演练或远端 CI。已有待审核消息时不能直接回退，不能报告“迁移可无条件回滚”。阶段 1 仍未验收。
- **清理**：复核 scope 后移除该专用容器及匿名卷，合成数据已删除，可按上述步骤重建；开发服务未改动。文档 `git diff --check` 退出 0。

## 2026-10-24 — 阶段 1：真实 Git 提交钩子拦截演练

- **隔离**：在系统临时目录新建独立 Git 仓库，复制当前 `.pre-commit-config.yaml` 与 `backend/pyproject.toml`；以本地 Python 3.13 / pre-commit 4.7.0、PYTHONUTF8=1 安装钩子。仅临时仓库设置合成 Git 身份；主项目索引、HEAD 和远端未修改。
- **故障一**：`backend/app/hook_probe.py` 含未使用的 `import os`，实际 `git commit` 退出 1，ruff-check 报 F401，format 通过。之后核对尚无 HEAD，文件仍含原导入，钩子未自动修复。
- **故障二**：将样例改为 `RESULT=1`，实际 commit 退出 1，ruff-check 通过，ruff-format 退出 1；`git diff --exit-code` 为 0（工作区与暂存内容一致），`git rev-parse --verify HEAD` 退出 1，仍没有生成提交，也未自动改写文件。
- **恢复**：样例改为 `RESULT = 1` 并重新暂存；commit 退出 0，两项 hook 通过，临时仓库生成唯一提交 62845d0，工作区干净。没有使用跳过 hook 的参数或环境变量。
- **项目复验**：当前主项目 `python -m pre_commit run --all-files` 两项通过，退出 0；此命令按 Git 已跟踪文件枚举，不能据此宣称未跟踪的新文件已全部覆盖。未跟踪 Python 文件仍需显式 Ruff 目录检查或加入索引后的 hook 验证。
- **边界**：这是本地 Git hook 的红/绿演练，不是 GitHub PR 测试失败、必需检查或分支保护证据，也不证明用户已经独立掌握操作。阶段 1 仍未验收。
- **补充检查与清理状态**：显式 Ruff 检查 app/tests/scripts 退出 0，格式检查 333 文件通过，覆盖目录内的新 Python 文件；git diff --check 退出 0。临时仓库删除请求被执行策略拒绝，未绕过，目录保留于 `C:\Users\qyf21\AppData\Local\Temp\codex-hook-drill-4a577025003149c1a82f5ce9a5a0a44a`，仅含复制配置、合成样例和演练 Git 历史。

## 2026-10-24 — 阶段 1：测试分层与标记校验

- **发现与调整**：LocalStack 测试模块已有显式环境开关，但缺少 e2e 标记；补充模块标记并保留原开关，未改变附件功能或开放入口。pytest 配置启用 --strict-markers，e2e 描述扩展为 Worker 或对象存储外部依赖。
- **选测验证**：Python 3.13 执行 `pytest tests/unit tests/scripts tests/integration --collect-only -q -m 'not e2e and not slow' -k 'not business_gold'`，**884/895 collected、11 deselected**，退出 0。这是收集结果，不是 884 项测试通过；较先前额外排除的是两项 LocalStack 测试，未减少普通集成断言。
- **边界验证**：即使设置 RUN_LOCAL_OBJECT_STORAGE_E2E=1，该模块在 `-m 'not e2e' --collect-only` 下仍为 2 deselected、退出 5（没有选中测试）；`-m e2e --collect-only` 恰好收集两项，退出 0，没有运行真实对象存储测试。
- **错误标记演练**：临时文件使用拼错的 pytest.mark.e2ee，指定项目配置收集时明确报未注册 marker，退出 1；临时探针随后删除。修改的测试模块 Ruff/格式检查通过。CONTRIBUTING 说明各层命令、环境开关、跳过边界及本地 Gold 排除与 CI 的差异。
- **未证明**：本轮未重跑行为测试、Python 3.12 或远端 CI；未读取 Gold JSON 内容，不将结构检查视为密封留出证据。阶段 1 未验收。

## 2026-10-24 — 阶段 1：远端发布前只读核对

- **GitHub 当前状态**：gh repo view 返回仓库 LeamrJohn/enterprise-insight-assistant 为公开仓库，默认分支 feature/api-contracts，当前账户 ADMIN。分支 API 返回远端 SHA a0d8578a94fc0d0c7759b018c23a5d530f83a391、protected=false；rulesets 数量为 0；开放 PR 列表为空。
- **运行证据**：最近运行列表仅返回 Dependency Graph 成功记录（run 30270658091，SHA c46071d7b85cb2ca4e5ff0bcdac317921cd4c935），不是本次 CI 配置的验证证据。
- **本地差异**：当前分支同为 feature/api-contracts，HEAD f00ea13a，暂存区为空。远端 SHA 是本地 HEAD 的祖先；本地已有 140007c1、5014131c、f00ea13a 三个尚未进入该远端分支的提交，另有本轮未提交改动。因此发布当前分支并非仅上传新增 CI 文件。
- **发布边界**：未提交、推送、创建 PR 或修改分支保护。须先由用户确认是否允许将既有三个提交及本轮经审查的工程基础改动发布到公开仓库的新分支；原有计划/evidence 修改须单独核对，不能夹带发布。实际 PR CI、故障演练、审查与学习验收仍待完成，不进入下一阶段冒充阶段 1 已完成。

## 2026-10-24 — 阶段 1：授权发布前复验与分批提交

- **授权与范围**：用户明确允许推送到公开仓库的新分支并创建草稿 PR，不合并。新建 codex/engineering-foundation-ci，保留此前三个重构相关提交；本轮按核心配置、分析/Runtime、Workflow、API/权限/观测、证据模块、冻结附件契约、脚本、CI/文档共八组提交。原有计划差异仅修正历史快照表述，未更改计划范围，随文档组纳入。
- **敏感内容检查**：Gitleaks v8.30.0 对 a0d8578a..HEAD 的三个历史提交扫描约 2.16 MB，退出 0；对当前工作区差异与全部未跟踪文件内容扫描约 664 KB，退出 0，均未命中。检查输出使用 redact；未将真实 .env、数据库转储或私钥纳入发布。模式扫描不能证明绝对无敏感信息。
- **最新回归**：独立 PG/pgvector 与 Redis（scope=pr-62c1），Python 3.13 执行 `pytest tests/unit tests/scripts tests/integration -m 'not e2e and not slow' -k 'not business_gold' -q --tb=short`，**882 passed, 2 skipped, 11 deselected in 45.25s**，退出 0。与先前差异为两项 LocalStack 场景从 skip 改为 e2e 排除，不是删除断言。
- **静态与提交**：Ruff 通过、333 文件格式通过、Pyright 0 errors/0 warnings、actionlint 退出 0；各代码组真实提交 hook 通过。完整回归针对分组前的组合工作树，不声称每个中间提交都独立跑过全套测试或远端 CI。
- **仍待验收**：草稿 PR 上的 CI、故意失败与恢复、必需检查、审查及用户独立操作。本记录不宣称阶段 1 完成，不授权合并或修改分支保护。

## 2026-10-24 — 阶段 1：草稿 PR 首轮 Compose 失败定位

- **发布**：已推送 codex/engineering-foundation-ci 并创建草稿 PR https://github.com/LeamrJohn/enterprise-insight-assistant/pull/1 ，未合并、未修改分支保护。PR 首轮 run 40145811939 的 Compose job 121026776182 明确报 backend/.env 不存在，退出 1；不是业务代码测试失败。
- **根因与复现**：docker-compose.yml 的服务 env_file 指向被忽略的 backend/.env；原本机 config 检查依赖本地文件，不能代替干净 checkout。临时目录仅复制 Compose 与 .env.example，config --quiet 同样退出 1；只补充示例副本为临时 backend/.env 后命令退出 0，未启动任何服务，未读取或覆盖真实 .env。
- **修复**：仅在 Compose CI job 加入 `cp backend/.env.example backend/.env`，继续执行原 config 检查；不降低运行环境必需配置要求，也不向工作流注入真实凭据。临时复现目录 codex-compose-ci-4c16e82f7ad54d8da7a57b9a4d5345ad 保留在系统 TEMP 中，仅含上述示例配置。
- **边界**：待新提交远端 CI 确认，其他 job 按实际结果记录；此修复不是全套 CI 已通过的声明。

## 2026-10-24 — 阶段 1：草稿 PR 首次 CI 全绿

- **对应版本**：PR #1，提交 7c6e4ce21234a43340d1452698ac0eaa1f80f9be，pull_request run https://github.com/LeamrJohn/enterprise-insight-assistant/actions/runs/40145893553 。watch 进程退出 0；API 确认 completed/success，七个 job 全部 success：Ruff、格式、Pyright、Backend unit、Backend integration、Frontend、Compose。
- **直接日志**：Backend unit job 121027054532 为 **794 passed, 2 skipped, 2 deselected in 23.83s**；Backend integration job 121027054449 为 **90 passed, 7 deselected in 11.06s**。两者分别运行，总计 884 passed；CI 包含本地回归排除的两项 Gold 文件检查，不据此宣称独立密封留出评测。被跳过或排除的测试仍未证明。
- **产物与边界**：API 确认 backend-unit-1、backend-integration-1 两个 JUnit artifact 存在且未过期。PR 仍为 OPEN/draft，head 与上述提交一致；未合并。mergeStateStatus=CLEAN 只表示当前平台合并状态，不证明已经配置必需检查。
- **剩余验收**：主动制造测试失败并恢复、实际必需检查/审查机制及用户独立操作尚未完成；此前意外 Compose 失败与恢复不能代替“用户主动设计并完成故障演练”的学习证据。阶段 1 尚未完成，后续阶段不因此自动开始。

## 2026-10-24 — 阶段 1：默认分支 PR 与必需检查规则

- **授权与变更**：用户明确允许后，新建 active ruleset 25808727（Default branch PR and CI gate），目标为默认分支，当前是 feature/api-contracts。规则要求 PR 和七项检查：Static (ruff)、Static (ruff-format)、Static (pyright)、Backend (unit)、Backend (integration)、Frontend、Compose configuration；检查来源绑定 GitHub Actions app 15368，strict_required_status_checks_policy=true。
- **读回验证**：ruleset API 与默认分支实际生效规则 API 均返回上述配置，bypass_actors 为空。未要求额外他人审批（required_approving_review_count=0），因此不能称为强制人工代码审查。PR #1 仍 OPEN/draft、mergedAt=null，未执行合并。
- **证据边界**：已证明规则配置及分支适用关系，尚未通过主动失败场景证明本规则下的拒绝行为；草稿 PR 自身也阻止合并，不能单凭草稿的不可合并状态归因于 CI 门禁。用户独立设计、实施、恢复与解释证据仍待验收。

## 2026-10-24 — 阶段 1：用户提出对照方案后的端口故障示范

- **学习来源**：用户提出“正常测试成功，改后失败”；补充恢复后再通过以加强因果证据。本轮由模型执行，只证明共同设计与示范，不标记用户独立操作已掌握。
- **隔离与变量**：新建 scope=port-drill-91ab 的独立 PG/pgvector 容器，复用初始化 SQL；同一个 test_conversation_migration_shape 测试使用 agent_platform_test，三次命令除 DATABASE_PORT 外保持相同环境，PGCONNECT_TIMEOUT=3。正确宿主端口 52387，错误端口 52388；不改变真实 .env、源码或数据库服务配置。
- **绿/红/绿**：端口 52387 时 **1 passed in 1.77s**、退出 0；改为 52388 时 **1 error in 3.77s**、退出 1，setup 阶段出现 sqlalchemy.exc.OperationalError / psycopg.errors.ConnectionTimeout，尚未执行测试体断言；pg_isready 同时确认专用数据库 accepting connections；恢复 52387 后 **1 passed in 0.20s**、退出 0。Ruff 全目录检查仍通过。
- **边界**：本机 Python 3.13 的单测试对照，不能替代远端 PR 故障注入、合并拒绝验证或用户独立练习。没有把连接超时错误写成业务断言失败，也没有修改业务状态以制造通过。

## 2026-10-24 — 阶段 1：远端端口故障与恢复提交

- **注入**：f9f967d3 仅在 CI 的 pytest 步骤增加 DATABASE_PORT=1、PGCONNECT_TIMEOUT=3 及注释；初始化和迁移仍使用正常端口。未提交同时存在的 README、数据生成脚本及知识库说明修改。
- **远端证据**：PR run 40165042308 completed/failure；Ruff、格式、Pyright、Frontend、Compose 成功，两项 Backend 失败。unit job 121084260043 的迁移成功、测试失败、Preserve test results 成功；integration job 121084259997 日志明确为 127.0.0.1:1 Connection refused，23 failed、67 errors、7 deselected。两个未过期 artifact（backend-unit-1、backend-integration-1）均存在。
- **恢复**：用 git revert 创建 34bc1c5c 并推送，删除三行故障设置，不改写失败提交历史，不删除失败日志。恢复版本远端结果尚待确认；不能提前把整个绿/红/绿演练算作完成。
- **边界**：未调用合并接口或取消草稿状态；已证明检查失败传播与报告保留，未单独实证合并拒绝的原因。执行由模型完成，学习能力不据此标记为独立掌握。

### 远端端口演练恢复结果

- 恢复提交 34bc1c5c 的 PR run https://github.com/LeamrJohn/enterprise-insight-assistant/actions/runs/40165345812 已完成，watch 退出 0，七项检查全部成功。unit 日志为 794 passed、2 skipped、2 deselected in 23.22s；integration 为 90 passed、7 deselected in 11.21s，两个 JUnit artifact 均存在且未过期。
- `git diff --exit-code 7760c34d HEAD -- .github/workflows/ci.yml` 退出 0，确认恢复版工作流与故障前一致。至此形成正常 run 40146087562 → 故障 run 40165042308 → 恢复 run 40165345812 的对照；失败记录未覆盖。
- PR 仍 OPEN/draft、mergedAt=null；没有发起合并或改动其他工作区修改。本结果证明远端失败传播与恢复，不证明独立人工审查、用户独立实施或实际合并拒绝，阶段 1 的学习验收仍未完成。

## 2026-10-24 — 阶段 1：排除草稿干扰的合并门禁对照

- **授权与基线**：用户要求进行验证；暂时将 PR #1 改为 ready for review，不执行合并。34bc1c5c 对应必需检查全部通过，isDraft=false、mergeStateStatus=CLEAN、mergedAt=null。规则 25808727 保持 active，要求七项 Actions 检查。
- **故障**：b24a47c8 仅向 pytest 步骤增加错误端口 1、连接超时 3 秒及注释。PR run https://github.com/LeamrJohn/enterprise-insight-assistant/actions/runs/40168274746 最终 failure；两个 Backend 失败，另外五个 job 成功。集成日志明确 127.0.0.1:1 Connection refused。所有检查结束后读取 PR：isDraft=false、mergeable=MERGEABLE（无代码合并冲突）、mergeStateStatus=BLOCKED、mergedAt=null。失败检查被 gh pr checks --required 列为必需检查，不以运行中 pending 状态代替最终失败证据。
- **恢复**：git revert 产生 9442b997 并推送；`git diff --exit-code 34bc1c5c HEAD -- .github/workflows/ci.yml` 退出 0。恢复 PR run https://github.com/LeamrJohn/enterprise-insight-assistant/actions/runs/40168465098 completed/success，七项检查全部通过；在仍非草稿时读回 mergeStateStatus=CLEAN、mergedAt=null。
- **收尾与范围**：对照期间目标分支 SHA 均为 a0d8578a94fc0d0c7759b018c23a5d530f83a391。最后恢复 PR 为 draft，API 确认 draft=true、merged=false。未修改分支规则、未调用合并接口、未提交工作区其他改动。此证据支持必需检查导致平台合并资格从 CLEAN→BLOCKED→CLEAN；没有冒险执行合并写入来测试拒绝响应，也不等于已完成独立人工审查或用户独立操作验收。

## 2026-10-24 — 阶段 1：初始化失败停止与恢复验证

- **最新 CI**：提交 f8339351 的 PR run 40169015644 与 push run 40169013328 均 completed/success；前一文档提交的运行被新提交取消，取消不计通过。
- **隔离与故障**：新建标签 codex.scope=bootstrap-drill-1024 的 pgvector 0.8.0/PG16 容器，无宿主端口映射，不连接开发数据库。省略 agent_platform 数据库，原样输入 bootstrap_postgres.sql 到 psql（ON_ERROR_STOP=1）。连接目标库时报不存在，psql 退出 3；随后查询 agent_migrator/agent_app 数量为 0，证明后续角色初始化未执行。
- **恢复与重复执行**：只补建 agent_platform 后，原脚本执行退出 0；再次执行也退出 0。两个项目数据库存在，agent_app/agent_migrator 均为非超级用户且无 BYPASSRLS。
- **边界与清理**：失败前 template1 的 vector 扩展已经创建，脚本不是全局原子事务；本结果证明遇错停止与该故障后的可重跑，不证明任意中间状态均可恢复，也不替代远端初始化故障证据。核对标签后删除本轮容器及匿名测试卷，临时数据可由初始化重建，未删除开发数据。命令由模型执行，学习验收仍待完成。

## 2026-10-25 — 落实原计划的上传入口冻结

- **问题与范围**：源码仍挂载文件上传和三项会话附件写入入口，前端仍有上传控件，旧测试要求 202；因此此前“入口已关闭”不是实现事实。本次按原计划关闭外部入口，不重做模块、不删历史数据，JSON 文档录入和读取保持不变。
- **实现**：文档文件上传归入不挂载的 upload_router；生产根路由不再挂载附件 router；前端移除文件/附件控件与对应事件处理。保留内部服务与客户端协议代码。旧模块测试仅使用独立 FastAPI 测试应用 frozen_upload_client，不改变生产 app；该测试应用复用请求上下文和错误处理。
- **红/绿验证**：新增四条 POST 拒绝与一条 OpenAPI 边界测试，修改前 5 failed（入口进入鉴权并返回 401、文档仍暴露上传）；修改后 5 passed。关闭后的 POST 返回 404/405，JSON `/documents` POST 仍在 OpenAPI 中。首轮全回归发现独立测试应用缺 request_id 中间件，补齐测试装配后重新运行，未放松生产入口断言。
- **回归**：专用 scope=freeze-1025 的 PGvector/PG16 与 Redis，loopback 49799/49802，应用 agent_app、迁移 agent_migrator；Python 3.13 执行 `pytest tests/unit tests/scripts tests/integration -m 'not e2e and not slow' -k 'not business_gold' -q -x --tb=short`，887 passed、2 skipped、11 deselected，40.82s，退出 0。Ruff 全目录通过，334 文件格式通过，Pyright 0 errors。前端 7 tests passed，TypeScript/Vite 构建通过；文档页面测试确认无文件控件且文本录入仍成功。
- **清理与边界**：核对标签后删除本轮两个容器及匿名测试卷，临时数据可重建，开发服务未操作。未部署或重启已有服务，未撤销历史直传授权，不证明已有运行进程已关闭入口或在途任务已停止；未运行 Worker/对象存储 E2E、旧 Gold 或真实模型评测。该变更恢复计划约束，不代表阶段 1 学习验收或阶段 2 完成。远端新提交 CI 结果待确认，PR 不合并。

## 2026-10-26 — 评测准备的文本接口契约

- **范围**：补充评测基线设计草案，不改原计划、评分器或业务代码。复用准备工具与 httpx MockTransport，用临时合成 fixture/文档验证实际请求序列；未读取旧 Gold 或新留出内容。
- **契约**：`_upload_documents` 只发送 JSON POST `/documents`，payload 严格等于文档名称、正文、来源与可见角色；标准答案哨兵不进入请求。随后 GET `/documents/73` 读取完成状态，并返回文档 ID、路径与 hash。不使用已冻结文件或附件上传入口。
- **验证**：`pytest tests/scripts/test_prepare_business_evaluation.py -k 'not cleanup' tests/unit/test_upload_entrypoints_frozen.py -q` 为 19 passed、1 deselected，0.61s，退出 0；修改测试文件 Ruff 和格式检查通过。排除的是需要数据库的清理测试，不宣称本轮执行真实 PG、Worker 或模型评测。
- **决策**：采用准备工具的窄契约回归；评测基线设计仍为草案，23 例开发集、7 例独立密封留出、真实运行预算和基线报告均未据此完成。三项原有工作区修改未纳入本切片。
