# P0-0 baseline/candidate prediction

## Scope

- Baseline code: Git `53723fb` (`v2.1.0`) in a detached worktree.
- Candidate code: the current dirty worktree; no claim is made about authorship.
- Shared harness: Python 3.13.14 and `backend/requirements-evaluation.txt` from the current evaluation harness.
- Shared test configuration: non-secret values from Git `HEAD:backend/.env.example`, overridden with `APP_ENV=test` and `DATABASE_NAME=agent_platform_test`.
- This slice changes only the audit harness and evidence process. It cannot prove Agent answer quality or production readiness.

## Already observed diagnostics

- The global Python 3.10 installation has incomplete `pip` and `pytest` packages.
- With one healthy isolated environment and explicit test configuration, baseline collects 338 tests and candidate collects 333 tests.
- The difference is 13 removed training-CRUD tests and 8 added production/evaluation tests. Test count alone cannot decide regression.

## Predictions before broader checks

- Ruff: candidate may fail because the large dirty worktree has not yet been linted as one unit; a failure must be classified by file ownership and candidate scope before fixing.
- Non-E2E/non-slow pytest: expected to fail or error when the PostgreSQL test database is unavailable; an environment failure must not be reported as a code regression.
- Full-corpus retrieval: the light environment intentionally lacks `sentence-transformers` and Torch, so it cannot prove real embedding retrieval quality.
- Real Celery/RAG/report E2E: not part of this first check; PostgreSQL, Redis, an independent Worker, business databases, vector retrieval and a model provider must be recorded separately.

## Decision rule

Do not adopt or reject the dirty candidate from totals. First classify each changed group as intended product change, evaluation candidate, unrelated change, or unresolved; then run the verification profile appropriate to that group.
