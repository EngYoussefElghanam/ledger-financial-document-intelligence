# LEDGER requirements and implementation review

Review date: 9 September 2026.

## 1. Overall assessment

The project has substantial building blocks, but the current checkout does **not meet the assignment's definition of done**. The main obstacles are broken real-service integration, the absent evaluation/observability service, insufficient enforcement of evidence grounding, and the absence of a reproducible held-out benchmark.

The strongest implemented parts are the Docling extraction boundary, structured document models, hybrid dense/BM25 retrieval with reranking, a genuinely conditional LangGraph workflow, basic answer-type validation, and a Gradio interface. These provide a useful foundation. However, a functioning mock UI and passing small unit tests do not establish a functioning PDF-to-answer system.

**Priority order:** connect the real pipeline; enforce evidence and calculation correctness; implement Langfuse and held-out evaluation; produce measured experiments and five traced failures; finish the required UI inspection and setup documentation; then demonstrate bonuses.

No numerical completion percentage or predicted grade is given: the PDF provides no weighted rubric, and several requirements need live evidence rather than source inspection.

### Post-review implementation update

After this review was written, the evaluation implementation described in
[`evaluation-implementation-plan.md`](evaluation-implementation-plan.md) was
added: eval-service APIs, TAT-DQA loaders/manifests, answer/retrieval/system
metrics, diagnostic propagation, reranker variants, Langfuse experiment support,
tests, and a seventh Compose service. The historical findings below describe the
checkout at review time. They should not be read as a new verification of live
held-out results: the complete corpus/services and configured Langfuse endpoint
still need to be run to produce those required artifacts and five real failures.

## 2. Scope, sources, and evidence limits

- Assignment: `C:/Users/nadaa/Downloads/Final_Project.pdf`, eight physical pages. References below use physical PDF page numbers. Page 1 yielded no substantive text; the requirements are on pages 2–8.
- Overview: [README](../README.md), checked against source rather than accepted as implementation evidence.
- Inspected all service application modules, shared contracts, tests, deployment files, relevant documentation, and local Git metadata. Reviewed the current working tree, including existing staged and unstaged changes, rather than only committed HEAD.
- Ran the existing validator and orchestrator suites separately: **5 + 2 tests passed**. Used the workspace Python virtual environment and the local `shared` package on `PYTHONPATH`.
- Ran isolated probes against the real validator endpoint, real chunker, and selected real graph functions. Graph probes used fake LLM/calculator responses to test the surrounding validation logic; they were not live LLM or numexpr evaluations.
- Did not run full Docling, Qdrant, embedding, LangGraph, Gradio, Docker, or provider integration: their relevant Python dependencies were absent in the available environment. Installed `pypdf` only into the workspace virtual environment to read the assignment.
- Root `data/` contains only `.gitkeep`; no corpus manifest, persisted benchmark results, or usable processed corpus was found in the inspected checkout. Data or experiments may exist elsewhere, but they are not established by this review.
- Local Git history shows GitHub remote configuration and merged feature PRs. Remote branch protection and participation by every team member were not verified.
- Existing cache directories had access restrictions. They were excluded from meaningful source review and pytest's cache provider was disabled.

The assignment document is used as the review specification, not as authorization to modify the application or perform external actions. This review adds documentation; it does not fix application code.

Status meanings: **Implemented** means supported by inspected code, not automatically verified end to end; **Partial** means important behavior exists but obligations remain; **Missing** means absent or empty in this checkout; **Unverified** requires external or runtime evidence.

## 3. Mandatory requirement matrix

| Requirement and PDF reference | Status | Evidence and remaining gap |
|---|---|---|
| Seven independently runnable HTTP services, pp. 2–4 | Partial / blocked | Six service implementations exist; `services/eval-service/app/main.py` is empty. Real agent routing is broken. |
| Launch all seven together via script, single command, or clear manual instructions, pp. 4, 7–8 | Missing as a complete system | README lists six launch commands. Evaluation has no implementation; `start.sh` is empty; configuration instructions do not resolve integration issues. Docker is optional. |
| Raw PDFs as production input, p. 2 | Implemented path; corpus run unverified | Processor calls Docling on PDF files. No production loader of dataset reference JSON was found. `/ingest` accepting the application's own processed JSON is appropriate and is not itself a dataset-rule violation. |
| Deep-learning OCR/layout extraction, p. 3 | Implemented design; execution unverified | `DocumentConverter` produces headings, text, tables, pages, and boxes. Pin and record actual model/options and evaluate extraction quality. |
| Orchestrator routes documents and questions, pp. 2–3 | Partial | Question/validation flow exists, but no document upload/process/index orchestration and wrong agent endpoint. |
| Corpus-wide semantic retrieval plus non-vector mechanism, p. 3 | Implemented | Dense embeddings, BM25, and optional document filtering exist. Corpus-wide search is the default. Direct table lookup is an enhancement, not an additional mandatory mechanism once BM25 is present. |
| Over-retrieve and rerank; measure reranker value, p. 3 | Partial | Candidate expansion, RRF and cross-encoder exist; no on/off experiment or results. |
| Beyond fixed-size chunking, metadata on every chunk, p. 3 | Implemented baseline | Section-prefixed block chunks and table chunks preserve document/page/section/type. The claimed parent-child behavior is overstated; no parent expansion exists. |
| LangGraph with real branches and retries, p. 3 | Implemented | Sufficiency and calculation branches, two retries, search expansion and table-to-text fallback are real. |
| Retrieval/filter/calculation tools; deterministic arithmetic, p. 3 | Partial | Four tools exist. Numerical route uses numexpr, but classification can bypass it; table and metadata tools filter a ranked sample, and operand grounding is unenforced. |
| Resource-efficient LLM, p. 3 | Unverified suitability | Hard-coded Groq model in `graph.py:15`; no measured token/cost/latency rationale. Provider availability and README quota claims were not verified. |
| FastAPI + Langfuse evaluation service, p. 3 | Missing | Evaluation service entrypoint, requirements and README are empty. LangSmith documentation does not fulfill the explicit Langfuse requirement. |
| Every request stage traced with latency/prompts/outputs/tokens, pp. 3, 8 | Missing | No Langfuse instrumentation or HTTP trace propagation found. Agent-level tracing alone would not expose retrieval reranking or validator internals. |
| Held-out automated TAT-DQA benchmark, pp. 3, 6, 8 | Missing | No dataset split manifest, question runner, reference-answer comparison, or result artifact. Processor batch evaluation measures structure only. |
| EM, F1, numerical accuracy, pp. 3, 6 | Missing | README claims of small successful runs are not reproducible metric reports. |
| Recall@K, Precision@K and MRR/Hit Rate where determinable, p. 6 | Missing | No relevance mapping or retrieval evaluator. |
| Average latency, calls/query, tokens, approximate cost, p. 6 | Partial | Orchestrator records total latency for successful `/ask` completion; other required metrics are absent. |
| Langfuse dataset experiments, p. 3 | Missing | No experiment definitions, variant configuration or measured comparison. |
| Five actual failed evaluation cases with Langfuse root causes, pp. 6, 8 | Missing as required deliverable | Agent README describes five failure modes, but lacks held-out example IDs, expected/predicted results and Langfuse traces. `docs/failure-analysis.md` is empty. |
| Gradio corpus-wide chat, pp. 3, 7 | Partial | UI and optional document scope exist; default mock mode bypasses real answering and validation. |
| Document inspection and dashboard, pp. 6–7 | Partial | Counts and lists exist, but processed documents are mislabeled indexed; actual extracted table contents are not exposed in the UI. |
| Document/page citations alongside answers, pp. 3, 7 | Partial | Renderer displays citation text for direct/calculated/multi-span responses; citations are not verified or openable. Opening pages is desirable; bounding-box highlighting is a bonus. |
| Typed four-answer schema and strict rejection, pp. 4–6 | Partial | All four models exist, but coercion, ignored extra fields, missing coverage checks, duplicate values and malformed-type errors violate strictness. |
| Required validator success/error logging, p. 4 | Mostly implemented | Required prefixes and common missing-field errors exist. Malformed `answer_type` values can cause unlogged server exceptions. |
| Insufficient evidence instead of guessing, pp. 5, 7 | Partial | Graph fallback and orchestrator rejection fallback exist; unsupported claims can still pass, outages are sometimes presented as missing evidence, and orchestrator-created fallback bypasses validator logging. |
| GitHub, protected main, feature branches, PRs, pp. 6, 8 | Partly evidenced / unverified | Remote and PR merge history exist locally. Branch protection and contributions from all team members require remote inspection. |
| Accurate setup/run README, p. 8 | Partial | Useful overview, but incomplete seven-service setup and several inaccurate claims/placeholders. |

## 4. Critical and high-priority failures

### F01 — The real orchestrator-to-agent request fails

**Priority: P0 — blocks the real demo.**

Evidence: [agent client](../services/orchestrator-api/app/agent_client.py), lines 44–55, posts to `/answer`; [agent API](../services/agent-service/app/main.py), line 34, exposes `/ask`.

With `USE_MOCK_AGENT=false`, the configured live agent receives an unknown route. `raise_for_status()` raises, and the orchestrator does not translate that exception into a controlled dependency response. Under these code paths, the UI cannot obtain a real answer through the orchestrator.

Fix: choose `/ask` consistently; add an HTTP contract test that exercises the actual client and actual agent route with graph execution stubbed. Then run a real PDF-to-answer smoke test.

### F02 — Default configuration hides the disconnected system

**Priority: P0.**

Evidence: UI `app/client.py:16,58–59` defaults `USE_MOCK=true`; orchestrator `agent_client.py:17,45–46` defaults `USE_MOCK_AGENT=true`. Both return random predefined answers unrelated to the question. UI mock responses bypass the validator entirely.

The integration now uses one canonical port map: processor **8001**, retrieval **8002**, agent **8003**, validator **8004**, evaluation **8005**, and orchestrator **8006**. Agent retrieval calls and UI/evaluation orchestrator calls follow that map.

Fix: provide one configuration template with correct URLs and explicit demo/mock flags; make the intended real launch path disable both mocks. Display mock status clearly when intentionally used. Verify the configuration actually loads: UI and orchestrator read process environment variables but do not load a root `.env` automatically; the agent loads a working-directory-relative `.env`.

Acceptance: a question scoped to one real document returns evidence from that document, and changing the question changes results through actual downstream calls.

### F03 — Processing does not make documents searchable

**Priority: P0.**

Evidence: processor `main.py:34–60,63–103` saves processed JSON; retrieval exposes separate `/ingest`; orchestrator has no ingestion endpoint or job runner. `scripts/download_dataset.py` is empty.

A successful upload or batch process creates no Qdrant points. The dashboard lists processed JSON files anyway and labels them indexed, so it can report documents that search cannot retrieve.

Fix: implement repeatable document routing: raw PDF → processor → retrieval ingestion → persisted status. Track `uploaded`, `processed`, `indexed`, and `failed` separately; only count confirmed indexed documents as searchable. Include resumable ingestion, failures, and stable dataset-ID mapping in a corpus manifest. A UI upload widget is useful but is not explicitly required by the PDF; a reproducible ingestion command/API can satisfy the demonstration.

### F04 — Mandatory evaluation and Langfuse are absent

**Priority: P0 — major assignment deliverable.**

`services/eval-service/app/main.py`, its requirements, and its README are empty. No Langfuse dataset/experiment integration or benchmark artifacts were found. Agent README sections describing LangSmith and two 8/8 runs are historical claims, not reproducible proof of the specified held-out evaluation.

Fix: implement the seventh FastAPI service and a benchmark runner; instrument all participating services with a shared trace/request ID. Record classification, candidate retrieval, reranking, tool inputs/results, answer generation and validation. Include latency, prompts/outputs, usage and errors at the appropriate spans. Document stages without LLM usage rather than inventing token counts.

Acceptance: run a versioned held-out manifest through real `/ask`, publish per-question predictions and aggregate metrics, open a trace spanning all relevant services, compare one variant, and document five actual failed examples.

### F05 — A valid citation shape does not establish grounding

**Priority: P0 — core correctness objective.**

Evidence: validator `main.py:33–78` checks models and citation presence only. It has no document or retrieval lookup. Direct/multi-span generation in `graph.py:267–306` allows the LLM to write document IDs and pages directly; the answer is not checked against retrieved chunks.

Confirmed: a direct answer citing `document_id="does_not_exist"`, page `99999`, value `"invented"` receives HTTP 200 with `valid: true`.

The PDF's validator subsection emphasizes schema checks, but its overall objective also requires checking answers against real retrieved evidence. That responsibility is currently missing across the combined pipeline.

Fix: preserve chunk/block/table identifiers in retrieval responses. Let generation select evidence IDs; resolve document/page metadata in trusted code. Verify that cited items exist, belong to the request's permitted scope and support each claim. For extracted facts, retain source spans/cells; use semantic support checks where a paraphrase cannot be checked by exact text matching. A model's self-assessment is not sufficient proof.

### F06 — Numerical answers can contain fabricated operands and incomplete citations

**Priority: P0.**

Evidence: `graph.py:194–235` checks formula characters and a nonempty index list, then calculates. It never verifies formula numbers against evidence text. The index condition is only `i < len(evidence)`, not a full integer/range check.

Isolated execution of the actual function, with evidence containing only “Revenue was 10” and a fake LLM emitting `999+1`, confirmed:

| Input indices | Actual behavior |
|---|---|
| `[0]` | Accepts a calculated answer citing the real chunk despite unsupported operands. |
| `[-1]` | Accepts Python's negative index as a citation. |
| `[0,999]` | Silently drops the invalid index and accepts the remaining citation. |
| `[-999]` | Raises `IndexError`. |
| `["0"]` | Raises `TypeError`. |

The calculator response was stubbed to isolate these guards; no claim is made about provider behavior or numexpr execution in this probe.

The validator independently accepts `formula="20+30"`, `value=999`, with one citation. Thus neither layer enforces the assignment's operand citation requirement or arithmetic/result consistency.

Fix: use a typed operand representation containing value, evidence ID, source span/cell, unit, scale, period and entity. Construct expressions from verified operands and separately permitted constants such as the `100` percentage multiplier. Require every referenced operand to resolve; reject invalid indices rather than dropping them. Recompute and compare the returned value under documented rounding/tolerance rules. Require finite results.

Repeated references to one operand and same-page operands need an explicit policy: count source operands, not every numeric token in the expression. Do not require document evidence for mathematical conversion constants.

### F07 — The answer contract is not strict enough

**Priority: P1.**

Evidence: [answer models](../shared/schemas/answer.py) use default Pydantic configuration. `MultiSpanParams` checks length only. `Answer` is a plain `Union`, despite being described as a discriminated union; no discriminator annotation is attached. The validator manually dispatches correctly for ordinary string types, but agent `AskResponse` has unrestricted `str`, `list` and `dict` fields.

Confirmed endpoint behavior:

- Numeric strings for calculated values and page numbers are coerced and accepted.
- Unknown fields are silently removed in the validator's normalized answer.
- `values=["Revenue","Revenue"]` passes despite the distinct-values requirement.
- Empty document ID, page `-1`, and boolean direct value pass; `true` becomes numeric `1`.
- `answer_type=[]` raises an unhashable-type exception and returns HTTP 500.
- Calculated evidence coverage and multi-span per-value support are not checked.

Fix: strict scalar types, `extra="forbid"`, a true discriminated union, finite numeric values, nonempty identifiers/formulas/reasons where semantically required, and a documented page-number convention. The assignment uses page 0 in its generic example; choose and consistently enforce a convention rather than assuming the PDF mandates one-based pages. Validate citation pages against actual documents. Check `answer_type` is a string before dictionary membership. Validate all generated answer shapes at the agent boundary too.

### F08 — Orchestration returns the unnormalized candidate and misses failure logging

**Priority: P1.**

Evidence: orchestrator `main.py:83–105` ignores `validation["answer"]` and returns the original candidate when valid. This can expose fields/types that differ from what the validator actually normalized. The rejected-answer replacement is generated after validation and is not itself submitted to the validator, so its required insufficient-evidence success logging is absent.

Network exceptions, downstream non-2xx results and unexpected downstream response shapes also bypass normal response handling. Retrieval tools turn all errors into evidence-shaped error lists, which can ultimately become an insufficient-evidence response even when the real issue is an outage.

Fix: return the validated normalized answer; validate/log the fallback; distinguish unsupported evidence from service failure; propagate trace IDs and controlled dependency errors. Keep public error text useful without exposing raw internal exception details.

## 5. Retrieval, reasoning and document-quality improvements

### F09 — Table and metadata filtering happen after ranked truncation

**Priority: P1.** Agent `tools.py:54–67` first retrieves general top-K results and removes non-tables. If the best table is ranked sixth with `limit=5`, table search returns no table even though one exists. `filter_documents`, lines 71–99, searches a generic query for 20 results and then applies section/type filters; it is not an exhaustive non-search metadata lookup as its docstring and README claim.

Fix: add server-side section/type filters to `SearchRequest` and apply them before candidate selection; expose paginated metadata listing or direct table retrieval separately. Normalize section labels without requiring the exact lowercase heading to match one of five hard-coded phrases. Evaluate filtered search against unfiltered retrieval. Document-filter placement in the Qdrant fused query should be covered by an installed-version integration test; this review does not assert an unverified Qdrant filtering bug.

### F10 — Chunking preserves some context but has no size or parent strategy

**Priority: P1.** `chunker.py:18–55` creates one chunk per paragraph/list item and one per entire table. It prefixes `block.section`; it does not attach the preceding heading object, maintain parent IDs, or retrieve larger parent context. Independent heading/caption content is not indexed unless carried into other fields. Whole tables and long blocks have no token budget, risking embedding/reranker truncation and LLM context pressure.

Confirmed: the repository fixture expects “Q3 European Cloud Sales” in its text chunk (`tests/test_main.py:60`), but the real output is `Section: Revenue ...`. The existing assertion would fail; the full retrieval suite was not run because its import loads unavailable model/database dependencies.

Fix: resolve the intended heading/section contract and make the fixture and implementation agree. Experiment with bounded section chunks and header-preserving table row groups, retaining a full table parent. Keep table IDs, row/column identity, units and page provenance. Measure recall and numerical answer quality before claiming improvement.

### F11 — Index identity and updates can leave misleading data

**Priority: P1.** Ingestion UUIDs depend only on `chunk.chunk_id` (`retrieval main.py:44`). Processor-generated IDs contain the document ID, but externally supplied schema-valid documents need not follow that naming rule. Two documents with block `b1` can overwrite each other. Reingesting a document with fewer chunks does not delete removed old points.

Fix: namespace point IDs by document ID plus chunk ID, validate duplicate IDs, and replace old document versions atomically or with explicit version/active-state handling. Verify same-document reingestion, shortened documents and cross-document identical block IDs. Return persisted ingestion counts/status, not only the number of chunks prepared in memory.

### F12 — Question routing can bypass deterministic arithmetic

**Priority: P1.** Invalid classification output falls back to `text` (`graph.py:53–58`), whose answer path is unconstrained generation. Therefore “always calculate through a tool” is not guaranteed when classification is wrong. Comparison, counting, ranking, and conditional multi-span questions may require structured operations beyond a single scalar arithmetic expression.

Evidence sufficiency uses `"yes" in answer` (`graph.py:136`). A probe with “No, not enough evidence to say yes” returns `is_sufficient=True`. Valid JSON with the wrong shape, such as an array, can also cause later `.get()` failures; only JSON decoding errors are handled.

Fix: typed classification/sufficiency/extraction outputs, exact enum handling, validated operation plans, deterministic counting/sorting where required, and a final check that derived numerical claims have a calculator/operation trace. Treat document text as untrusted evidence in prompts and test instruction-like content inside retrieved passages. An evidence-grounding check remains necessary even with better prompting.

### F13 — Extraction loses provenance details and hides empty pages

**Priority: P1/P2.** Processor `processor.py:52–60,115–126` uses the first provenance entry only. Items spanning pages lose additional page/box information. `_bbox_to_list` copies coordinates without retaining origin/page dimensions; later highlighting cannot safely infer the coordinate system. Missing table provenance defaults to page 0 and an all-zero box.

`processor.py:143–150` constructs pages only from extracted items, so empty/unrecognized pages disappear. `batch_eval.py:31–34` then looks for empty pages only inside that list: it cannot detect pages already omitted by the processor. A file can have a larger `page_count` without the structural report flagging those missing pages.

Fix: retain every physical page, explicit missing-provenance status, page dimensions/orientation and normalized coordinate conventions. Preserve relevant multi-page provenance. Validate row lengths against declared columns, all table counts, unique page/item IDs, and valid page references. Add extraction comparisons against reference data used strictly as evaluation ground truth.

The processor's existing fixture test documents a known wrapped-cell limitation; it checks table counts rather than the correctness of all financial cell values. Expand fixtures to merged headers, wrapped labels, parentheses negatives, scales, percentages, multi-page tables and scanned pages. Schema-valid rows do not establish accurate extraction.

### F14 — File handling permits path escape and collisions

**Priority: P1, especially before accepting other users' uploads.** Processor `main.py:50,132` joins untrusted upload filenames and supplied document IDs directly into filesystem paths. Parent-relative or absolute paths can escape the intended directories under the service account's permissions. This is a static code finding; no exploit or destructive write was performed.

MIME/extension checks do not verify PDF contents, upload size/page counts are unrestricted, and same-name uploads or IDs can overwrite each other. Persistence is non-atomic and uses platform-default text encoding. `/process_batch` accepts arbitrary server-side directories.

Fix: generate safe storage names; constrain and validate IDs; resolve paths and check containment; use size/page limits and proper PDF validation; write UTF-8 JSON atomically; record hashes and collision policy. Limit batch access to an intended corpus root. Apply access control if exposed beyond a trusted local demo; this is an operational improvement, not a separate assignment checkbox.

### F15 — Concurrency and latency behavior are fragile

**Priority: P2.** Retrieval's async endpoints execute synchronous embedding, reranking and Qdrant work inline. This can block the event loop. Local Qdrant storage is hard-coded relative to the working directory, and multiple server processes need a deliberate storage strategy. Models and collection initialization occur during import, making startup/readiness and tests expensive or failure-prone.

The agent can make three retrieval calls of up to 30 seconds each, plus several LLM calls. UI and orchestrator each allow about 60 seconds for their downstream answer request; a legitimate retry path may outlive the caller. No coordinated deadline/cancellation policy exists.

Fix: explicit startup/lifespan initialization, readiness checks, bounded concurrency/work queues or appropriate synchronous endpoints, configurable persistent storage, and measured overall deadlines. Use a Qdrant server if independent workers need concurrent access. Distinguish transient transport retries from semantic evidence retries, and bound both.

## 6. UI and dashboard gaps

**Priority: P1 for truthful inspection; P2 for performance and convenience.**

- `_to_ui_summary` in orchestrator `main.py:55–65` throws away actual extracted tables/blocks and always returns `structured_values={}`. The Documents UI shows a table count, not the table. The required table-understanding demonstration needs the real table representation, through a UI detail panel or clearly demonstrated API output.
- Named financial-value extraction is not mandatory as a separate feature when unavailable; however, the system already extracts structured table rows and should expose those real values rather than fabricated mock fields or an always-empty placeholder.
- The Dashboard tab lists document IDs, names and pages. Table counts exist only in Documents. Bring actual table summaries into the corpus dashboard or link directly to useful inspection.
- Citation rendering in `format_answer.py:17–30` is text only. Add a source-PDF/page endpoint and open-page links; preserve citation identity for later highlighting.
- `insufficient_evidence` rendering hides evidence even if an answer includes optional citations. Display supporting search context when present and useful.
- `chat_tab.py:19` receives history but does not send it to the backend. Follow-ups such as “what about last year?” have no conversational context. This is a missing bonus, not a mandatory base-chat failure.
- Orchestrator document listing performs one list request plus **N sequential full-document requests**. Dashboard and Documents load separately, potentially repeating that work. At corpus scale, use a persisted summary/index-status endpoint with pagination and bounded fetching.
- `_recent_queries` grows indefinitely although only the last ten are returned. Bound it with a deque or persist deliberately. It resets per process/restart and excludes failed requests; document those semantics or include error status and timing.
- Dashboard/document callbacks lack the chat callback's error handling, so dependency outages can fail whole panels. Give panels explicit loading, error and empty states.
- The HTML answer formatter escapes interpolated values, which is a good existing protection. Visual rendering itself was not browser-tested in this review.

## 7. Every bonus feature

The PDF says bonus credit requires a demonstrated effect, not just implementation. **No bonus has sufficient demonstration evidence in this checkout.**

| Bonus | Current status | Work needed and demonstration |
|---|---|---|
| All seven services in Docker Compose, p. 7 | Missing | Compose is empty; five Dockerfiles are empty. Complete all services, URLs, volumes, readiness and configuration, then demonstrate one-command startup and persistent ingestion after restart. |
| Bounding-box citation highlighting, p. 7 | Missing; extraction groundwork exists | Boxes exist in processed JSON but disappear from retrieval/answer evidence. Retain source IDs, page geometry and coordinate origin; render cited boxes on the actual page and demonstrate correct alignment. |
| Query decomposition, multi-query retrieval, or HyDE, p. 7 | Missing | Top-K expansion repeats the same question; it is not decomposition or multi-query retrieval. Split a multi-company/period question into evidence subqueries, merge/deduplicate results and measure recall/accuracy versus baseline. One demonstrated option can satisfy this bullet. |
| Contextual retrieval, semantic caching, conversation memory, p. 7 | Limited contextual baseline; other parts missing | Section prefixes provide some context but are already part of required chunking, with no separate contextual-retrieval experiment. No cache or backend history exists. Demonstrate a concrete contextual variant, safe scoped cache, or memory with measurable effect. Cache keys need corpus version and document scope. |
| SQL/structured-data querying beside vector search, p. 7 | Missing | Table strings in Qdrant and post-filtered semantic results are not structured querying. Add typed financial records or table-cell queries with provenance; demonstrate exact lookup/aggregation and compare with vector-only results. |
| Human correction of extracted fields, p. 7 | Missing | UI tables are read-only. Add a correction action with source reference, original/new value, audit/version history, reindexing and cache invalidation. Demonstrate an extraction error corrected through to a changed supported answer. |
| Rich company-level financial dashboard, p. 6 | Missing | Basic corpus dashboard exists. Company/period/currency/scale normalization and substantive financial views are absent. Only attempt after required inspection and evaluation; short excerpts may not support broad company comparisons. |

The processor Dockerfile uses the repository root build context and installs the shared package before service requirements. Its standalone and Compose configurations now both listen on port **8001**. A full Docker build is still required in environments where the ML dependencies and model downloads are available.

Suggested bonus order after core completion: source-page highlighting; query decomposition for cross-document questions; complete Compose; structured lookup; memory/cache; human correction; rich company dashboards. Select based on measured bottlenecks rather than feature count.

## 8. Testing, reproducibility and documentation

### What was actually verified

| Check | Result | Limit |
|---|---|---|
| Existing answer-validator suite | 5 passed | Covers a few valid/missing-field cases, not real evidence or strict typing. |
| Existing orchestrator suite | 2 passed | Both downstream clients are mocked; wrong HTTP endpoint is invisible. |
| Validator adversarial probes | Five invalid/unsupported cases accepted; unhashable type returned 500 | Deterministic local TestClient results. |
| Chunker fixture expectation | Heading assertion evaluates false | Real chunker and fixture; model/database suite not executed. |
| Graph guard probes | Unsupported numbers and invalid indices accepted; other indices crash; misleading “yes” parsed true | Actual function bodies with fake LLM/calculator dependencies. |
| Full seven-service integration, extraction accuracy, model quality, browser UI, Docker | Not run | Dependencies/services/corpus unavailable in the review environment. |

To repeat the existing lightweight suites from the repository root in PowerShell, set `PYTHONPATH` to the absolute `shared` directory and run each service's tests in its own working directory with the environment's Python:

```powershell
$env:PYTHONPATH = (Resolve-Path shared).Path
# In services/answer-validator-api, using your activated environment:
python -m pytest tests -q -p no:cacheprovider
# Run the same command separately in services/orchestrator-api.
```

Do not interpret the passing suites as a clean repository-wide test result. Multiple services use identical `app` and test module names; separate processes/environments or deliberate import configuration are needed for an aggregate runner.

### Tests to add or repair

1. Real HTTP client/route contract checks, including mock-off configuration and validator-returned normalization.
2. Raw fixture PDF → processed document → ingestion → search → agent → validator, plus unanswerable and dependency-down cases.
3. Every strict-answer type boundary, unknown/extra fields, booleans, coercion, duplicate spans, finite numbers, malformed types and required logging.
4. Evidence existence/scope, source-operand matching, invalid/mixed indices, wrong result/formula, units/scales, zero denominator and classification bypass.
5. Filtered table recall, metadata lookup coverage, reingestion deletion and cross-document chunk-ID collisions.
6. Extracted financial cell accuracy and missing-page detection across representative fixtures.

Processor API tests currently remove the configured `PROCESSED_DIR` with `shutil.rmtree` before each test. They were not run here. Replace production-path fixtures with `tmp_path`-backed directories before running alongside valuable local data. Retrieval tests use the real working-directory database and model loads rather than an isolated fixture; use temporary collections/storage and separate unit from integration tests.

### Reproducibility problems

- Most heavy dependencies are unpinned or only lower-bounded. UI `gradio>=4.44` spans potentially different APIs. No runtime compatibility claim was tested here; choose a tested version set and lock it.
- Validator and orchestrator requirements install `ledger-shared` from **different Git commit hashes**, whereas agent/processor install local shared code and retrieval omits an explicit shared dependency. Services can disagree about the very contract intended to unify them. Standardize on the reviewed local package or one release/version across services.
- The shared package does not declare its Pydantic runtime dependency. Individual service setup should not depend on incidental installations.
- Agent LLM is hard-coded and an unused Google integration is imported. Make provider/model configuration explicit and record the tested model with benchmark results. Do not treat README rate-limit claims as established measurements.
- `start.sh`, root `.env.example`, `docker-compose.yml`, dataset downloader, `docs/answer-schema.md`, and `docs/failure-analysis.md` are zero-byte placeholders.
- README describes some empty Dockerfiles and supporting files as functional. Agent README claims 100% schema compliance and verified operand grounding, which the probes disprove. It also calls metadata filtering a direct non-search lookup, although it performs `/search`.
- The root README is candid about some integration gaps, but it is primarily a file tour. Add an exact tested install/configure/ingest/run/evaluate sequence for all seven services, including working directories and mock flags.

## 9. Minimum credible evaluation design

This is a proposed completion plan, not a claim that experiments were performed.

A file-level implementation plan, metric contract, trace design, API proposal,
test matrix, and definition of done are in
[`evaluation-implementation-plan.md`](evaluation-implementation-plan.md).

1. **Freeze data identity.** Download the raw PDF corpus and Q/A annotations through a documented process. Record hashes, dataset revision and PDF-to-document-ID mapping. Production extraction uses only PDFs; reference parsed tables/text belong in evaluation/debugging paths.
2. **Create separate development and held-out manifests.** Record the selection seed and IDs. Include direct, multi-span, arithmetic, counting/comparison and corpus-wide questions. Keep held-out questions/answers out of prompt tuning. Indexing the underlying documents is appropriate; leaking their gold answers into the answering pipeline is not.
3. **Run the real public pipeline.** Default to no supplied document ID for the corpus-wide benchmark. If using oracle document scope diagnostically, report it separately; it does not prove corpus-wide retrieval.
4. **Store one record per question.** Include gold/predicted answer, answer type, supporting references, candidate/reranked IDs, formula and source operands, normalized metrics, latency, calls, tokens, approximate cost, error status, trace ID and configuration version.
5. **Define metrics before comparing variants.** Specify text normalization, multi-span matching/order handling, numerical absolute/relative tolerance, percentage and scale treatment, and refusal/error scoring. Report failures and denominator counts; do not silently drop timeouts or unparseable outputs.
6. **Measure retrieval at an honest granularity.** Map gold evidence to your extracted pages/cells/chunks where possible. Report Recall@K, Precision@K and MRR/Hit Rate with the relevance unit and mapping coverage. Do not invent exact chunk labels when only document-level relevance is known.
7. **Compare a controlled variant.** Minimum: same data/model/prompts with reranker on/off. Record quality plus latency/cost. Then investigate chunking or metadata filters. Use Langfuse datasets/experiments as required.
8. **Select five real failures.** Each needs question ID/text, expected and actual result, source PDF/page/table, trace ID/link, first failing stage, concrete diagnosis, proposed fix and measured retest. Generic potential failures in this review cannot substitute for these examples.

An initial small stratified pilot can debug the harness, followed by a larger frozen held-out set. The assignment specifies no minimum benchmark size; report the chosen size and limitations explicitly.

## 10. Repair roadmap and acceptance criteria

| Order | Deliverable | Acceptance criterion |
|---|---|---|
| 1 | Real configuration and endpoint alignment | Both mocks off; correct `/ask` and retrieval port; a real downstream request completes through the orchestrator. |
| 2 | Repeatable raw-PDF ingestion and truthful index state | A newly processed PDF produces persisted searchable chunks; failed ingestion is visible; dashboard counts only indexed documents. |
| 3 | Strict schemas and grounded calculations/claims | All invalid probes above are rejected; valid direct, calculated, multi-span and insufficient-evidence answers pass; every source/operand resolves. |
| 4 | Seventh service and cross-service Langfuse | One trace shows all relevant stages, usage, timing and validation; errors/refusals remain observable. |
| 5 | Held-out evaluator and controlled experiment | Versioned predictions, required metrics and reranker comparison reproducible with documented commands. |
| 6 | Five traced failures | Five real held-out examples with first failing stage and evidence-backed diagnoses. |
| 7 | Required UI inspection and full setup | Inspect real tables and source pages; all seven services launch via a documented tested procedure. |
| 8 | Selected bonuses | Each chosen bonus has a real demonstration and measured or visibly verified effect. |

P0 denotes a core correctness or system-completion blocker; P1 denotes an important requirement/reliability gap; P2 denotes an improvement to address after blockers. Deployment hardening recommendations are distinguished from assignment requirements throughout.

## 11. Final demo readiness checklist

- [ ] Show a raw PDF and the application's own processed JSON.
- [ ] Show an extracted financial table, including actual rows and values.
- [ ] Ask a corpus-wide question without a document ID and retrieve the correct source.
- [ ] Show a numerical question using verified source operands and the deterministic calculator.
- [ ] Display the answer's real source page/table.
- [ ] Walk through one executed conditional LangGraph path, including retry or refusal where appropriate.
- [ ] Open one real Langfuse trace spanning the request stages.
- [ ] Present held-out answer, retrieval and system-performance metrics.
- [ ] Show a controlled change that measurably helped or hurt.
- [ ] Present one real traced failure live and include at least five documented cases.
- [ ] Launch all seven services through the documented procedure.
- [ ] Verify GitHub protection/PR collaboration requirements separately.
- [ ] Demonstrate the effect of every bonus claimed.

The project is ready for completion work, but should currently be described as an implemented set of service components with unfinished integration and evaluation. The highest-value next step is proving a real, grounded, traced path from one raw PDF through the public UI before scaling to the held-out corpus benchmark.
