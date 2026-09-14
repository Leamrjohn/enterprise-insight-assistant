# Candidate scope V1

Baseline is Git `53723fb`. Candidate measurement includes only these changes:

- `backend/app/core/rag/embeddings_local.py`: multilingual 384-dimension embedding model.
- `backend/app/core/rag/retrieval.py` and `backend/app/repositories/vector_repository.py`: question-aware character-bigram candidate reranking.
- `docs/business_knowledge_base/manifest.json` and its newly added corpus files.
- `backend/tests/evaluation/test_full_corpus_retrieval_evaluation.py` and `backend/tests/evaluation/test_finally_answer.py`.

All other current working-tree changes, including archived-file deletion and broad documentation/API cleanup, are non-comparison changes. They remain untouched and must not affect a baseline-versus-candidate metric conclusion.

Run the independent evaluation image with:

```powershell
docker compose --profile evaluation run --rm evaluation python -m pytest tests/evaluation -q
```

The default image is intentionally light and runs deterministic contract tests.
The full-corpus embedding evaluation uses the separate heavyweight image:

```powershell
docker build -f backend/Dockerfile.evaluation-full -t agent-evaluation-full backend
```
