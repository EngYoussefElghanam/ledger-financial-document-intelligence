# Evaluation implementation plan

This plan turns the evaluation requirements in
[`project-requirements-review.md`](project-requirements-review.md) into an
implementable, reproducible benchmark. The benchmark must call the real public
question-answering path with mocks disabled; it must not score a direct LLM call
or a gold-document shortcut as the main result.

Implementation status (9 September 2026): the evaluator, dual-format loader,
manifest generator, deterministic metrics, resumable run storage, diagnostics,
variant control, Langfuse propagation/experiment command, tests, and seven-service
Compose entry are implemented. The frozen practice manifest is
`data/evaluation/manifests/2d95de53424cc9c5.json`. Publishing measured quality
results and five real failures still requires the full indexed corpus, all
question-answering services, and the configured Langfuse endpoint to be running.

## 1. Required outcome

For a frozen held-out subset of TAT-DQA, run:

```text
question -> orchestrator /ask -> agent -> retrieval -> answer validator
         -> predicted answer -> deterministic comparison with ground truth
```

The evaluator lives in `services/eval-service` and calls the public
orchestrator interface. Small, opt-in changes to the orchestrator, agent,
retrieval API, answer validator, shared schemas, and service startup are also
included so the real pipeline can propagate trace context and expose evaluation
diagnostics without changing the normal UI response contract.

Produce all of the following:

- Answer quality: Exact Match (EM), token F1, and numerical accuracy.
- Retrieval quality where a gold-to-retrieved mapping is possible: Recall@K,
  Precision@K, MRR, and Hit Rate@K.
- System performance: end-to-end latency, LLM calls per query, input/output/total
  tokens, and approximate cost.
- One Langfuse trace per question, with child observations for every material
  stage and explicit errors/refusals.
- At least one controlled experiment, initially reranker enabled versus disabled.
- Versioned local artifacts and a Langfuse dataset run.
- Five real failed held-out cases with trace-backed root-cause analysis.

The main report must include every attempted question. Timeouts, dependency
failures, malformed answers, and refusals count in the denominator; they must
never be silently discarded.

## 2. Evaluation prerequisites

These are inputs and acceptance checks for the evaluator, not implementation
tasks in the other services:

1. **Use the real path.** The pilot must call orchestrator `/ask` with mocks
   disabled. Do not add a second answering path to the evaluator.
2. **Record available diagnostics.** Consume stable retrieval IDs, ranks, scores,
   scales, citations, request IDs, and trace IDs when the public response or
   trace exposes them. If a diagnostic is unavailable, store `null` or
   `unavailable` and exclude only that metric's scorable denominator.
3. **Control variants at the boundary.** Accept only `reranker_on` and
   `reranker_off`; pass the selected variant using the existing service
   configuration/interface and record the resolved value in every run.
4. **Freeze runtime configuration.** Store model/provider, prompt version,
   temperature, K values, corpus identity, code commit, dependency lock, and
   environment name in the run configuration. The evaluator must not mutate
   these values.
5. **Separate service failures from refusals.** Preserve timeout, dependency,
   malformed-answer, and refusal statuses in item results and denominators.

## 3. Proposed code and artifact layout

```text
services/eval-service/
  app/
    main.py                 FastAPI endpoints and run lifecycle
    models.py               Strict request/result schemas
    dataset.py              TAT-DQA loader, split, and Langfuse import
    answer_adapter.py       LEDGER answer -> TAT-DQA prediction
    runner.py               Calls the real orchestrator and persists each item
    storage.py              Atomic local run/artifact storage
    langfuse_client.py      Dataset, experiment, score, and flush helpers
    metrics/
      answer.py             EM, F1, numerical accuracy
      retrieval.py          Recall/Precision/MRR/Hit Rate and mapping coverage
      system.py             Latency, calls, tokens, cost, and error rates
  tests/
    fixtures/               Small synthetic TAT-DQA-style fixtures
    test_dataset.py
    test_answer_metrics.py
    test_retrieval_metrics.py
    test_system_metrics.py
    test_runner.py
  requirements.txt
  README.md

scripts/
  prepare_tat_dqa_eval.py   Create immutable development/held-out manifests
  run_evaluation.py         Submit a run, wait, and print artifact locations

data/evaluation/
  manifests/                Versioned IDs and hashes; safe to commit
  runs/<run_id>/            Generated artifacts; normally gitignored
```

Do not copy evaluation code into `src/ledger-shared`. Keep one canonical shared
package and one canonical eval-service implementation.

## 4. Dataset and held-out split

### 4.1 Source identity

Use the official raw PDFs for production ingestion. Use the official QA JSON,
OCR JSON, answers, scales, facts, and block mappings only in evaluation and
debugging code. Record:

- TAT-DQA source URL/revision and license;
- SHA-256 for every source annotation file and selected PDF;
- dataset document UID to LEDGER document ID mapping;
- manifest-generation code version and seed.

The TAT-DQA site describes each question with a question UID, document UID,
answer, answer type, derivation, scale, facts, and optional block mapping. Its
official prediction format is `[answer, scale]`; reuse the official evaluation
implementation for comparable EM/F1 rather than creating a subtly different
clone.

### 4.2 Split policy

- Prefer the official development split for development and the released test
  ground truth for the final held-out run.
- If a custom subset is necessary, split by **document UID**, not by question,
  so questions from one document cannot appear in both tuning and held-out sets.
- Select documents deterministically by hashing `seed + document_uid`; write the
  selected IDs to an immutable JSONL manifest.
- Stratify/check coverage for `span`, `spans`, `arithmetic`, and `counting`, plus
  table/text/table-text evidence and comparison questions.
- Keep held-out answers out of prompts, retrieval content, caches, and tuning.
  Indexing the held-out PDFs is expected and is not answer leakage.
- The primary benchmark is corpus-wide (`document_id=null`). An oracle-document
  run may be reported only as a separately labeled diagnostic upper bound.

Start with a small stratified pilot to debug the harness, then freeze a larger
held-out manifest. State the sample size and limitations because the assignment
does not prescribe a minimum.

## 5. Evaluation service API

Implement the seventh independently runnable FastAPI service on port 8005.

| Endpoint                       | Purpose                                                                      |
| ------------------------------ | ---------------------------------------------------------------------------- |
| `GET /health`                  | Liveness plus Langfuse/storage readiness, without exposing secrets.          |
| `POST /datasets/import`        | Validate a frozen manifest and upsert its items to a named Langfuse dataset. |
| `POST /runs`                   | Start a run and return `202`, `run_id`, status URL, and configuration hash.  |
| `GET /runs/{run_id}`           | Progress, attempted/completed/failed counts, and terminal status.            |
| `GET /runs/{run_id}/metrics`   | Aggregate and sliced metrics with denominators.                              |
| `GET /runs/{run_id}/items`     | Paginated per-question outcomes and trace IDs.                               |
| `GET /runs/{run_id}/artifacts` | Paths/links for predictions, metrics, config, and failures.                  |

`POST /runs` should accept a manifest ID, run name, variant, K values, concurrency,
and orchestrator URL. Limit variants to known values. Default concurrency to 1
for the first reproducible run and increase it only after rate-limit behavior is
measured.

The runner must call the same orchestrator `/ask` path used by the UI. Diagnostic
data may be returned in response headers or fetched by trace ID, but must not use
a second answering implementation. Persist each item immediately so a stopped
run can resume without repeating completed questions.

## 6. Per-question result contract

Store one JSONL row per attempted question with at least:

```json
{
  "run_id": "...",
  "question_id": "...",
  "document_id": "...",
  "question": "...",
  "gold": { "answer": "...", "answer_type": "...", "scale": "..." },
  "prediction": { "raw": {}, "answer": "...", "scale": "..." },
  "answer_metrics": { "em": 0.0, "f1": 0.0, "numerical_accuracy": null },
  "retrieval": {
    "mapping_level": "chunk|page|document|unavailable",
    "mapping_coverage": 1.0,
    "candidate_ids": [],
    "reranked_ids": [],
    "metrics_by_k": {}
  },
  "system": {
    "status": "ok|refusal|timeout|dependency_error|invalid_answer",
    "latency_ms": 0.0,
    "llm_calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "cost_usd": null,
    "retries": 0
  },
  "trace_id": "...",
  "config_hash": "..."
}
```

Use `null`, not zero, when usage or cost is unavailable. Zero means it was
measured and no units were used.

## 7. Metric definitions

### 7.1 Answer metrics

1. **EM and F1:** emit the official TAT-DQA prediction shape and call the
   official evaluator. Preserve its normalization and scale semantics. Add unit
   tests copied from documented examples so upgrades cannot silently change
   scores.
2. **Numerical accuracy:** evaluate only gold `arithmetic` and `counting`
   questions. Parse finite numeric values after removing display separators.
   Normalize using the explicit predicted and gold scales, then mark correct when
   `abs(pred-gold) <= max(abs_tolerance, rel_tolerance * abs(gold))`. Freeze the
   tolerances in run configuration; proposed defaults are `1e-4` absolute and
   `1e-3` relative. Scale mismatch is incorrect unless normalization proves the
   values equivalent.
3. **Multi-span:** retain the official evaluator's order-insensitive behavior.
   Do not join values into an ambiguous sentence before scoring.
4. **Refusals/errors:** map them to an empty prediction for answer scoring and
   also report refusal and error rates separately.

Report macro overall EM/F1, numerical accuracy, and slices by gold answer type,
evidence source, document/page count, and system status. Include numerator and
denominator for every metric.

### 7.2 Retrieval metrics

For relevance set `R`, returned ranking `L`, and cutoff `K`:

- `Recall@K = |R intersect L[:K]| / |R|`
- `Precision@K = |R intersect L[:K]| / K`
- `HitRate@K = 1` if any relevant item occurs in the first K, else `0`
- `MRR = 1 / rank_of_first_relevant_item`, or `0` when there is no hit

Report at `K = 1, 3, 5, 10` unless the run configuration says otherwise. Score
candidate retrieval and final reranked retrieval separately; also retain the
final evidence after retries.

TAT-DQA block IDs do not automatically equal Docling chunk IDs. Build relevance
at the strongest defensible level:

1. chunk/cell mapping when a gold fact or block span can be deterministically
   aligned to an extracted chunk;
2. page mapping when only the source page can be resolved;
3. document mapping when only the gold document UID is known;
4. unavailable when none can be established.

Never mix levels into one unlabeled number. Report metric denominators and
`mapping_coverage = scorable_questions / attempted_questions` for each level.
Add a small manually checked mapping sample to estimate alignment errors.

### 7.3 System metrics

Measure client-observed end-to-end latency around the orchestrator call and
report mean, median, p95, min, and max. From trace observations report:

- mean LLM generation calls per attempted query;
- input, output, and total tokens per query and in total;
- approximate USD cost per query and in total;
- retry count, timeout rate, dependency-error rate, invalid-answer rate, and
  refusal rate;
- optionally, embedding/reranker calls and their latency, clearly separated from
  LLM calls.

Prefer provider-reported token usage. Langfuse can infer cost when a recorded
model matches a configured model definition; otherwise store the provider usage
and a versioned price table. Label cost as approximate and record the currency,
price source, and effective date.

## 8. Langfuse tracing design

Use one root trace per question and nested observations similar to:

```text
evaluation.question
  orchestrator.ask
    agent.graph
      classify_question              generation
      retrieve_evidence              span
        dense_search                 embedding/span
        bm25_search                  span
        rrf_fusion                   span
        cross_encoder_rerank         span
      check_evidence_sufficiency     generation
      extract_operands               generation, numerical route only
      calculate                      tool/span
      generate_answer                generation when used
    validate_answer                  span
  score_answer                       span
  score_retrieval                    span
```

Record prompts and outputs on generation observations, model and parameters,
provider usage, start/end time, errors, candidate IDs/ranks, selected evidence,
calculation inputs/results, validation output, request ID, dataset item ID,
variant, and config hash. Do not label deterministic retrieval or calculation as
an LLM generation and do not invent token counts for it.

Use standard distributed trace-context propagation across HTTP boundaries and a
separate human-readable request ID. Redact credentials and avoid sending entire
PDFs to Langfuse. Flush telemetry before marking a run complete, then verify that
every completed item has a trace. Missing required traces should make the run
`completed_with_errors`, not silently successful.

Import the frozen held-out items into a versioned Langfuse dataset and use an SDK
dataset experiment so deterministic scores attach to each item and aggregate at
run level. Store the Langfuse dataset/run URL in the local artifact manifest.

## 9. Controlled experiments

The first required comparison is:

| Run | Reranker | Everything else |
| --- | -------: | --------------- |
| A   |  enabled | frozen          |
| B   | disabled | identical to A  |

Use the same manifest, corpus snapshot, model, prompts, temperature, K, and
concurrency. Compare EM, F1, numerical accuracy, Recall/Precision/MRR/Hit Rate,
latency, tokens, calls, cost, errors, and mapping coverage. Do not claim the
reranker helped based only on retrieval quality if end-to-end answer quality or
latency regressed.

Because LLM APIs can remain nondeterministic at temperature zero, report the
exact run IDs. If resources permit, repeat each variant or rerun a smaller
stability sample and report variance. Subsequent experiments should target an
observed bottleneck, such as table chunking or server-side metadata filtering.

## 10. Persisted artifacts

Each run directory should contain:

- `manifest.json`: dataset hashes, question IDs, corpus identity;
- `config.json`: full resolved configuration and config hash, excluding secrets;
- `predictions.json`: official TAT-DQA submission/evaluator format;
- `items.jsonl`: every per-question record, including failures;
- `metrics.json`: aggregate and sliced metrics with denominators;
- `summary.md`: concise human-readable tables and limitations;
- `failures.json`: automatically ranked incorrect/error cases;
- `run.log`: lifecycle events without secrets;
- `langfuse.json`: dataset name/version, experiment/run ID, and URL.

Write files atomically and mark a run immutable when complete. A rerun gets a new
run ID. Commit small manifests, schemas, and final summarized results; normally
exclude raw PDFs, secrets, local vector storage, and large trace exports.

## 11. Five-case failure analysis

After the frozen run, choose five actual failures across different first-failing
stages when possible: extraction, retrieval, reranking, reasoning/calculation,
and validation/system failure. For each case add to `docs/failure-analysis.md`:

- question UID and text;
- gold and predicted answer/scale;
- source PDF, page/table, and gold evidence;
- trace ID/link and run/config hash;
- first failing stage, not merely the final symptom;
- concrete evidence for the diagnosis;
- proposed change;
- retest result, clearly labeled if not yet implemented.

Do not substitute hypothetical failure modes for executed held-out cases.

## 12. Tests and quality gates

### Unit tests

- answer normalization: punctuation, articles, case, commas, signs, percentages,
  scales, zero, negative values, lists, duplicates, and Unicode;
- numerical tolerance boundaries, non-finite values, and wrong scales;
- retrieval formulas, K larger than result count, multiple relevant items, no
  hit, and unavailable mapping;
- deterministic document-level split, no overlap, hashes, and stratification;
- token/cost aggregation with missing usage distinguished from zero;
- serialization round trips and strict rejection of unknown fields.

### Integration tests

- fake orchestrator -> eval runner -> persisted artifacts -> aggregate metrics;
- interrupted run resumes without duplicate rows;
- timeout/dependency/invalid-answer/refusal all remain in denominators;
- Langfuse disabled or unavailable produces an explicit unhealthy/error state;
- variant propagation reaches retrieval and is recorded;
- trace ID is preserved across orchestrator, agent, retrieval, and validator.

### End-to-end acceptance

On a small real-PDF fixture, verify PDF processing, indexing, corpus-wide `/ask`,
validation, scoring, artifact creation, and a complete Langfuse trace. Then run
the frozen held-out set with both variants.

## 13. Evaluation implementation order

1. Implement and unit-test the official-format answer adapter and deterministic
   answer, retrieval, and system metric modules.
2. Implement the dataset loader, document-level split/manifest generator, source
   hashing, and optional Langfuse dataset import.
3. Implement strict request/result models and resumable local artifact storage.
4. Implement the runner against the existing orchestrator `/ask` endpoint;
   persist one terminal item result immediately after each attempt.
5. Expose the eval-service API and CLI; document its standalone command and
   environment variables.
6. Run a small stratified pilot and fix evaluator or mapping defects without
   using final held-out scores for tuning.
7. Freeze and execute reranker-on/off held-out runs, generate artifacts, and
   verify counts against the manifest.
8. Write five trace-backed failures and the final comparison report.

## 14. Definition of done

Evaluation is complete only when all statements below are true:

- A documented command starts eval-service independently and it reports healthy.
- A versioned, hashed held-out manifest has no document overlap with tuning data.
- Every manifest item has exactly one terminal result row, including failures.
- The runner uses real orchestrator `/ask` with both mocks disabled and no oracle
  document scope in the primary run.
- EM, F1, numerical accuracy, retrieval metrics with mapping coverage, and system
  metrics with denominators are persisted and reproducible.
- Each completed question has a usable Langfuse trace with generation usage and
  stage timings, or the run explicitly reports the missing trace as an error.
- Reranker-on/off runs share the same frozen configuration except for the named
  variant and have a written comparison.
- Five real failed cases are documented with trace-backed root causes.
- Setup documentation starts the evaluator independently and documents the
  existing service prerequisites needed to reproduce the pilot run.

## 15. Additional gaps discovered while planning

These items were easy to miss in the original metric list but should be included:

- scale/unit representation for fair TAT-DQA numerical scoring;
- stable chunk identity and separate candidate/final ranks for retrieval metrics;
- mapping coverage and relevance granularity beside every retrieval score;
- p50/p95 latency, refusal/error rates, and metric denominators;
- trace completeness and telemetry failure as a quality gate;
- immutable config/corpus hashes and resumable item-level persistence;
- document-level rather than question-level splitting;
- controlled concurrency and rate-limit reporting;
- a manually audited sample of gold-to-Docling evidence alignment;
- an extraction-only diagnostic/upper bound, because retrieval cannot recover a
  value that PDF processing omitted;
- repeatability/stability checks for nondeterministic hosted models;
- an explicit distinction between primary corpus-wide results and oracle-document
  diagnostic results.

## References

- TAT-DQA dataset and official evaluation format:
  <https://nextplusplus.github.io/TAT-DQA/>
- TAT-DQA repository: <https://github.com/NExTplusplus/TAT-DQA>
- Langfuse offline dataset evaluation:
  <https://langfuse.com/docs/evaluation/get-started/offline>
- Langfuse SDK experiments:
  <https://langfuse.com/docs/evaluation/experiments/experiments-via-sdk>
- Langfuse token and cost tracking:
  <https://langfuse.com/docs/observability/features/token-and-cost-tracking>
