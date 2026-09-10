# Evaluation service

For the tested local Docker workflow and dataset prerequisites, see
[local-evaluation-workflow.md](../../docs/local-evaluation-workflow.md).

The seventh LEDGER service runs a frozen TAT-DQA manifest through the real
orchestrator `/ask` endpoint, records every attempted item, and calculates:

- answer Exact Match, token F1, and numerical accuracy;
- separate pre-rerank candidate and final reranked Recall@K, Precision@K,
  Hit Rate@K, and MRR where gold provenance can be mapped to returned
  chunks/pages/documents;
- mean/median/p95 latency, LLM calls, tokens, approximate cost, retries,
  refusals, and error rates;
- Langfuse-linked per-question traces and deterministic scores when configured.

It accepts both the official nested TAT-DQA JSON from
<https://huggingface.co/datasets/next-tat/TAT-DQA/tree/main> and the extended
flat practice format in `data/questions_setA_practice.json`.

## Configuration

Set these in the repository-root `.env`:

```dotenv
EVAL_DATASET_PATH=C:/absolute/path/to/questions_setA_practice.json
EVAL_DATA_DIR=C:/absolute/path/to/data/evaluation
ORCHESTRATOR_URL=http://localhost:8006

# Required for the final compliant benchmark, optional for local metric tests.
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_REQUIRED=true

# Provider price snapshot used for approximate cost in local artifacts.
LLM_INPUT_COST_PER_MILLION=0
LLM_OUTPUT_COST_PER_MILLION=0
LLM_PRICE_SOURCE=provider pricing page
LLM_PRICE_EFFECTIVE_DATE=YYYY-MM-DD
```

Keep both application mocks disabled for a real run.

## Run locally

From the repository root in PowerShell:

```powershell
python -m pip install -r services/eval-service/requirements.txt
python scripts/prepare_tat_dqa_eval.py data/questions_setA_practice.json
Set-Location services/eval-service
python -m uvicorn app.main:app --host 0.0.0.0 --port 8005
```

Submit a run from a second repository-root terminal:

```powershell
python scripts/run_evaluation.py data/evaluation/manifests/<manifest-id>.json `
  --variant reranker_on --require-langfuse
```

Repeat with `--variant reranker_off`. Do not compare the runs if their manifest,
corpus, model, prompts, K values, or other configuration changed.

To create the required Langfuse dataset experiment (after `POST /datasets/import`
has uploaded the dataset), run:

```powershell
python scripts/run_langfuse_experiment.py tat-dqa-held-out `
  --run-name ledger-reranker-on --variant reranker_on
```

The experiment SDK creates the Langfuse dataset run and item traces. The task
propagates its active trace/parent IDs through orchestrator, agent, retrieval,
and validation.

## API

- `GET /health`
- `POST /datasets/import`
- `POST /runs`
- `POST /runs/{run_id}/resume`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/metrics`
- `GET /runs/{run_id}/items`
- `GET /runs/{run_id}/artifacts`

Generated runs are stored under `data/evaluation/runs/<run-id>/`. Timeouts,
dependency errors, malformed answers, and refusals remain in the denominator.
Each run includes `metrics.json`, the official `[answer, scale]`
`predictions.json`, all per-item records, failures, frozen manifest metadata,
Langfuse status, and a Markdown summary.
An oracle-document run is supported only as a separately labeled diagnostic;
the primary result must remain corpus-wide.
