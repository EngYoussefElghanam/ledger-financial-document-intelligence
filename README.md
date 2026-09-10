# LEDGER: Financial Document Intelligence

LEDGER is a service-based system for asking questions about a collection of
financial PDF documents. It extracts text and tables from PDFs, indexes the
extracted content, retrieves relevant evidence, uses an agent to produce a
typed answer, validates that answer, and displays the result in a Gradio UI.

This document explains how the project works and what each file does. It is
also a map of the current implementation: some services are complete enough
to run independently, while the final multi-service wiring still needs local
configuration and a few integration fixes.

## 1. What The Project Does

The project follows this pipeline:

```text
PDF files
	|
	v
doc-processor-api       Docling extraction and ProcessedDocument JSON
	|
	v
retrieval-api           Chunking, embeddings, Qdrant ingestion and search
	|
	v
agent-service           Question classification, retrieval, reasoning and answer creation
	|
	v
answer-validator-api    Strict answer schema and evidence validation
	|
	v
orchestrator-api        Public backend that coordinates agent and validator
	|
	v
ui-service               Gradio chat, dashboard and document browser
```

The normal lifecycle is:

1. A PDF is uploaded or selected from a local directory.
2. `doc-processor-api` converts it into the shared `ProcessedDocument` model.
3. The processed document is persisted as JSON under `data/processed`.
4. A caller sends that JSON to retrieval `/ingest`.
5. `retrieval-api` creates text/table chunks and stores dense and sparse
   vectors in Qdrant.
6. A user asks a question through the UI or orchestrator `/ask`.
7. The agent retrieves evidence, decides whether the question is textual,
   tabular, or numerical, and creates a typed answer.
8. The orchestrator sends the answer to the validator.
9. A valid answer reaches the UI. An invalid answer is replaced with an
   `insufficient_evidence` answer instead of being shown as fact.

## 2. Repository Layout

```text
ledger-financial-document-intelligence/
|-- data/                         Runtime uploads, processed JSON and local data
|-- docs/                         Architecture and failure-analysis notes
|-- scripts/                      Dataset/download helpers
|-- services/
|   |-- doc-processor-api/        PDF extraction service
|   |-- retrieval-api/            Hybrid retrieval service
|   |-- agent-service/            LangGraph reasoning service
|   |-- answer-validator-api/     Answer contract validation service
|   |-- orchestrator-api/         Backend coordinator and UI-facing API
|   `-- ui-service/               Gradio application
|-- shared/
|   |-- schemas/                  Pydantic contracts shared by services
|   `-- document.schema.json       Exported document JSON schema
|-- docker-compose.yml            Intended multi-service deployment entrypoint
|-- start.sh                      One-command Docker Compose startup
`-- README.md                     This project guide
```

## 3. Shared Contracts

### `shared/schemas/document.py`

Defines the document model produced by the processor and consumed by
retrieval:

- `Block`: a heading, paragraph, list item, or caption with text, section,
  and bounding box.
- `Table`: a structured table with rows, columns, caption, section, and
  bounding box.
- `Page`: page number plus its blocks and tables.
- `ProcessedDocument`: document id, original filename, page count, and pages.

Bounding boxes use `[x0, y0, x1, y1]`. The model is the main contract between
document extraction and indexing.

### `shared/schemas/answer.py`

Defines the strict answer contract used by the agent and validator. The
`answer_type` discriminator selects one of four answer models:

- `direct`: one value, with at least one evidence citation.
- `calculated`: numeric value and formula, with evidence citations.
- `multi_span`: at least two values, with evidence citations.
- `insufficient_evidence`: a reason; evidence may be empty.

`Evidence` contains `document_id`, `page`, and an optional `section`. The
validator uses these models to reject missing fields, invalid types, unknown
answer types, and unsupported empty citations.

### `shared/schemas/search_request.py`

Defines the retrieval request: a query, optional document id, and result
limit.

### `shared/schemas/export_schema.py`

Generates `shared/document.schema.json` from the Pydantic document model. It
is a small utility script rather than a runtime service.

### `shared/schemas/__init__.py`

Re-exports shared document schema classes so services can import them through
the shared schema package.

### `shared/document.schema.json`

JSON Schema representation of the processed document contract. It is useful
for external consumers and for checking the shape of persisted document JSON.

## 4. Document Processor Service

Directory: `services/doc-processor-api`

This service is the only component that directly understands Docling. It
accepts PDFs and returns the normalized shared document model.

### `services/doc-processor-api/app/processor.py`

Contains the extraction implementation:

- Creates one reusable Docling `DocumentConverter`.
- Converts Docling bounding boxes into four-number lists.
- Maps Docling item types to the project content types.
- Tracks the current heading so later blocks receive their section name.
- Converts tables into structured rows instead of only flattened text.
- Assigns stable block and table ids based on document and page.
- Builds `ProcessedDocument` pages in page-number order.

Keeping Docling logic here means the FastAPI layer does not depend on Docling
internals.

### `services/doc-processor-api/app/main.py`

FastAPI HTTP layer and persistence boundary:

- `GET /health`: returns a liveness response.
- `POST /process`: accepts one PDF upload, processes it, persists JSON, and
  returns the full `ProcessedDocument`.
- `POST /process_batch`: processes every PDF in a server-side directory and
  returns success/failure counts.
- `GET /documents/{document_id}`: loads one persisted processed document.
- `GET /documents`: lists persisted document ids.

The service writes uploads to `data/uploads` and processed JSON to
`data/processed`. These directories are created when the module starts.

### `services/doc-processor-api/app/warmup.py`

Warmup helper intended to load Docling models before normal requests. This
reduces the latency of the first real conversion.

### `services/doc-processor-api/app/explore_docling.py`

Development/exploration script for inspecting Docling output while the
document mapping was being built. It is not part of the request path.

### `services/doc-processor-api/batch_eval.py`

Batch evaluation utility for running structural checks over a PDF sample.
It supports continuing from an offset so large document collections can be
processed incrementally.

### `services/doc-processor-api/tests/test_main.py`

Tests the FastAPI surface, including processing and document-list behavior.

### `services/doc-processor-api/tests/test_processor.py`

Tests the Docling-to-shared-schema conversion logic.

### `services/doc-processor-api/tests/fixtures/`

PDF and other test fixtures used by processor tests.

### `services/doc-processor-api/Dockerfile`

Container definition for the document processor. It installs the service
dependencies and starts the FastAPI application.

### `services/doc-processor-api/requirements.txt`

Python dependencies for FastAPI, Docling, Pydantic, and related processing
libraries.

### `services/doc-processor-api/pyproject.toml`

Project/tooling metadata for this service.

### `services/doc-processor-api/README.md`

Service-specific notes about installation, processing, and validation.

## 5. Retrieval Service

Directory: `services/retrieval-api`

Retrieval turns structured documents into searchable chunks and uses a hybrid
dense/sparse search pipeline.

### `services/retrieval-api/app/chunk_schema.py`

Defines `Chunk`, which contains a chunk id, searchable text, and metadata.

### `services/retrieval-api/app/chunker.py`

Converts a `ProcessedDocument` into chunks:

- Paragraph and list-item blocks become text chunks prefixed with their
  section.
- Tables become readable text containing section, caption, and row data.
- Metadata preserves document id, page number, content type, and section.

This metadata is returned with search results and becomes the source for
answer citations.

### `services/retrieval-api/app/embeddings.py`

Loads and exposes three models:

- `BAAI/bge-small-en-v1.5` for dense semantic vectors.
- `Qdrant/bm25` for sparse keyword vectors.
- `cross-encoder/ms-marco-MiniLM-L-6-v2` for final reranking.

The functions batch dense and sparse embedding calls, then score the smaller
candidate set with the cross-encoder.

### `services/retrieval-api/app/database.py`

Creates the local Qdrant client and initializes the `financials` collection.
The current implementation uses filesystem storage at `./qdrant_data` with a
384-dimensional dense vector and a BM25 sparse vector.

### `services/retrieval-api/app/main.py`

Retrieval API endpoints:

- `POST /ingest`: accepts a `ProcessedDocument`, creates chunks, embeds them,
  and upserts Qdrant points with deterministic UUIDs.
- `POST /search`: embeds the query, performs dense and sparse searches,
  fuses results with reciprocal rank fusion, reranks candidates, and returns
  the requested number of text/metadata results.

The optional `document_id` filter restricts results to one document.

### `services/retrieval-api/tests/test_main.py`

Tests retrieval endpoint behavior and request/response handling.

### `services/retrieval-api/README.md`

Service-specific setup and retrieval notes.

### `services/retrieval-api/requirements.txt`

Dependencies for FastAPI, Qdrant, FastEmbed, sentence-transformers, and
shared schemas.

## 6. Agent Service

Directory: `services/agent-service`

The agent is the reasoning layer. It uses LangGraph to run a controlled
workflow rather than asking an LLM to answer without an explicit evidence
step.

### `services/agent-service/app/main.py`

Exposes:

- `GET /health`: agent liveness check.
- `POST /ask`: accepts a question and optional document id, invokes the graph,
  and returns an answer-shaped object.

The request rejects blank questions. Unexpected graph errors become HTTP 500
responses. If the graph returns no answer, the endpoint falls back to
`insufficient_evidence`.

### `services/agent-service/app/graph.py`

Builds the LangGraph reasoning workflow:

1. `classify_question` labels the question as `text`, `table`, or
   `numerical`.
2. `retrieve_evidence` searches retrieval, optionally filtering by document
   and known financial sections.
3. `check_evidence_sufficiency` asks the model whether the retrieved context
   can answer the question.
4. On insufficient evidence, `increment_retry` expands the search from 5 to
   10 to 15 results. Table questions can fall back to general text search.
5. Numerical questions go through `extract_and_calculate`.
6. `generate_answer` creates a direct or multi-span answer from evidence, or
   returns a deterministic calculated answer.
7. Failed calculations or exhausted retries route to
   `insufficient_evidence`.

Numerical answers are deliberately guarded: the model must cite the evidence
chunk for every operand, formulas are restricted to arithmetic characters,
and `numexpr` performs the actual calculation.

### `services/agent-service/app/tools.py`

Defines the tools used by the graph:

- `calculate`: strips currency separators and evaluates an arithmetic
  expression with `numexpr`.
- `search_documents`: calls retrieval `/search` for general evidence.
- `search_tables`: calls retrieval and keeps table-type results.
- `filter_documents`: searches with metadata restrictions for a document,
  section, or content type.

The retrieval base URL is controlled by `RETRIEVAL_API_URL`.

### `services/agent-service/graph.png`

Visual diagram of the LangGraph workflow.

### `services/agent-service/README.md`

Detailed agent design notes, usage instructions, failure analysis, and
Langfuse tracing notes.

### `services/agent-service/requirements.txt`

Dependencies for LangGraph, LangChain model integrations, Groq/Google model
clients, HTTP calls, `numexpr`, and environment loading.

## 7. Answer Validator Service

Directory: `services/answer-validator-api`

This service is the trust boundary before an answer reaches the user.

### `services/answer-validator-api/app/main.py`

Exposes:

- `GET /health`: validator liveness check.
- `POST /validate_answer`: accepts raw JSON and returns `{valid, answer}` or
  `{valid: false, reason}`.

Validation happens in three stages:

1. Confirm that `answer_type` is known.
2. Require evidence for `direct`, `calculated`, and `multi_span` answers.
3. Validate the complete type-specific Pydantic model.

It also prints the required success/error log formats and extracts the first
missing field name for readable error messages.

### `services/answer-validator-api/tests/test_validate_answer.py`

Tests valid answer types, missing evidence, missing type-specific fields, and
unknown answer types.

### `services/answer-validator-api/README.md`

Describes the validator contract and expected logs.

### `services/answer-validator-api/requirements.txt`

Dependencies for FastAPI, Pydantic, and annotations used by the service.

## 8. Orchestrator Service

Directory: `services/orchestrator-api`

The orchestrator is intended to be the only backend called by the UI. It
coordinates the agent, validator, and document processor.

### `services/orchestrator-api/app/main.py`

Exposes:

- `GET /health`: orchestrator liveness check.
- `POST /ask`: calls the agent, validates its answer, and returns either the
  valid answer or an `insufficient_evidence` fallback.
- `GET /documents`: proxies and reshapes document-processor results for the
  UI.
- `GET /documents/{document_id}`: returns one reshaped document summary.
- `GET /dashboard`: returns document count, document summaries, and the last
  ten in-memory queries with latency.

The recent-query dashboard is intentionally non-durable and resets on restart.
Document `structured_values` are currently returned as an empty object because
the extraction pipeline does not yet identify named financial values.

### `services/orchestrator-api/app/config.py`

Centralizes downstream URLs:

- `DOC_PROCESSOR_URL`, default `http://localhost:8001`
- `RETRIEVAL_URL`, default `http://localhost:8002`
- `AGENT_SERVICE_URL`, default `http://localhost:8003`
- `ANSWER_VALIDATOR_URL`, default `http://localhost:8004`

Docker deployments can replace these values with service-name URLs.

### `services/orchestrator-api/app/agent_client.py`

Calls the agent service or returns deterministic mock answers when
`USE_MOCK_AGENT=true`. Live mode is the default and calls agent `/ask`;
dependency failures become controlled HTTP 502 responses.

### `services/orchestrator-api/app/validator_client.py`

Sends candidate answers to validator `/validate_answer` and returns the
validator response.

### `services/orchestrator-api/tests/test_ask.py`

Mocks agent and validator clients to test both orchestrator outcomes: passing
through a valid answer and replacing an invalid answer with an
`insufficient_evidence` answer.

### `services/orchestrator-api/README.md`

Documents the orchestration contract, mock mode, and downstream service URLs.

### `services/orchestrator-api/requirements.txt`

Dependencies for FastAPI, HTTPX, Pydantic, and service communication.

## 9. UI Service

Directory: `services/ui-service`

The UI is a Gradio application with three tabs. It should call the
orchestrator, not the lower-level services directly.

### `services/ui-service/app/main.py`

Creates the Gradio application, registers Chat, Dashboard, and Documents
tabs, loads dashboard/document data on page load, and launches on
`0.0.0.0`.

### `services/ui-service/app/client.py`

HTTP client for the orchestrator:

- `ask_question`: sends `/ask` requests.
- `get_dashboard_data`: loads `/dashboard`.
- `get_documents`: loads `/documents`.
- `get_document_detail`: loads `/documents/{document_id}`.

`USE_MOCK=false` is the default. `ORCHESTRATOR_URL` controls the real backend
location, and an explicit banner always identifies live or mock mode.

### `services/ui-service/app/components/chat_tab.py`

Builds the chat view, accepts an optional document scope, calls the client, and
formats errors or answers for display.

### `services/ui-service/app/components/dashboard_tab.py`

Builds the document count, indexed-document table, and recent-query table. It
loads data on startup and supports manual refresh.

### `services/ui-service/app/components/documents_tab.py`

Lists documents, allows a row to populate a document id, and displays page,
table, and structured-value details.

### `services/ui-service/app/components/format_answer.py`

Renders the four answer types as escaped HTML. It displays values, formulas,
multi-span lists, insufficient-evidence reasons, and evidence citations.

### `services/ui-service/app/theme.py`

Contains the Gradio theme and custom CSS used for the LEDGER visual identity.

### `services/ui-service/requirements.txt`

Dependencies for Gradio, HTTP requests, and UI rendering.

## 10. Evaluation Service

Directory: `services/eval-service`

The seventh FastAPI service loads either official nested TAT-DQA annotations or
the extended flat practice set, creates a deterministic held-out manifest, runs
every question through orchestrator `/ask`, and persists per-item predictions,
EM/F1/numerical accuracy, retrieval metrics, latency, LLM calls, tokens, cost,
errors, and trace IDs. It also supports Langfuse dataset import and SDK
experiments for reranker-on/off comparison.

See [`services/eval-service/README.md`](services/eval-service/README.md) for the
API and commands, and
[`docs/evaluation-implementation-plan.md`](docs/evaluation-implementation-plan.md)
for the metric contract and acceptance criteria.

## 11. Supporting Files

### `docs/architecture.md`

Architecture notes and service port information. It is useful for deployment
planning and for keeping service boundaries consistent.

### `docs/answer-schema.md`

Describes the expected answer shapes and evidence rules.

### `docs/failure-analysis.md`

Records known failure modes and mitigations across retrieval, reasoning,
calculation, verification, and model limits.

### `scripts/download_dataset.py`

Dataset download helper for obtaining the financial PDF corpus. It is used
during data preparation rather than normal API requests.

### `docker-compose.yml`

Starts the complete seven-service graph with health checks, persistent corpus
and model volumes, local source mounts, and the canonical port map.

### `start.sh`

Validates Compose and starts the complete stack with a build. It creates a
local `.env` from `.env.example` when needed. Run `./start.sh -d` for detached
startup; Windows users can run `docker compose up --build` directly.

### `.env.example`

Template for model keys, service URLs, and runtime switches. Copy the values
into a local `.env` file and never commit real credentials.

### `.dockerignore` and `.gitignore`

Exclude local environments, caches, generated artifacts, and other files that
should not enter images or version control.

### Service `Dockerfile` files

Each service Dockerfile defines its runtime image, dependency installation,
working directory, and startup command. The API services use Uvicorn; the UI
uses the Gradio application entrypoint.

### `__init__.py` files

Mark application and shared directories as Python packages. Most are empty;
the shared schema initializer also exposes commonly used schema classes.

## 12. Running The Individual Services

The exact dependency set is service-specific. From each service directory,
install its `requirements.txt`, then run the relevant entrypoint.

Typical commands are:

```powershell
# Document processor
python -m uvicorn app.main:app --reload --port 8001

# Retrieval API
python -m uvicorn app.main:app --reload --port 8002

# Agent service
python -m uvicorn app.main:app --reload --port 8003

# Answer validator
python -m uvicorn app.main:app --reload --port 8004

# Orchestrator
python -m uvicorn app.main:app --reload --port 8006

# Evaluation service
python -m uvicorn app.main:app --reload --port 8005

# UI
python -m app.main
```

When running a service from its own directory, ensure the `shared` directory
is available on `PYTHONPATH` or install the shared package according to the
repository setup. Configure downstream URLs with environment variables when
the services are not using their defaults.

## 13. Current Integration Status

Implemented building blocks:

- PDF extraction and persistence.
- Structured document and answer schemas.
- Hybrid retrieval with Qdrant.
- LangGraph agent workflow.
- Answer validation and fallback behavior.
- Orchestrator document/dashboard endpoints.
- Gradio UI with explicit live/mock mode.
- Held-out TAT-DQA evaluation service, deterministic metrics, artifacts, and
  Langfuse experiment support.

Items to verify before calling the full system production-ready:

- Run the live PDF smoke script with configured model credentials before a demo.
- Complete or verify Docker Compose service definitions, shared volumes, and
  health checks.
- Configure real model credentials and retrieval model downloads.
- Run both reranker variants on the frozen held-out manifest and publish the
  measured artifacts plus five traced failures.
- Add document structured-value extraction.

## Real end-to-end demo

For Docker Desktop, use the [Docker runbook](docs/docker-runbook.md). Compose
now defines all seven services, persistent volumes, and health checks. You can
start only the UI/orchestrator/validator while disk space is limited; document
answers require the remaining services and a configured Groq key.

For the complete Windows setup, TAT-DQA download, service startup, ingestion,
verification, recovery, and shutdown procedure, follow
[`docs/windows-tat-dqa-runbook.md`](docs/windows-tat-dqa-runbook.md).

Copy `.env.example` to the repository-root `.env`, provide the model key, and
leave both `USE_MOCK=false` and `USE_MOCK_AGENT=false`. Every service resolves
that same file from its source location, so its working directory does not
change configuration loading.

Ingest one PDF through the complete processor-to-retrieval route:

```powershell
python scripts/ingest_corpus.py path/to/pdf-directory
```

`GET /ingestion` reports `uploaded`, `processed`, `indexed`, and `failed`
records. Failed retrieval writes remain resumable, and `GET /documents` plus
the dashboard only count retrieval-confirmed `indexed` documents. To verify
the complete live path with two distinct questions:

```powershell
python scripts/smoke_pdf_to_answer.py path/to/report.pdf "First question" "Second question"
```

The safest way to understand a request is to follow the contracts: documents
enter through `ProcessedDocument`, chunks carry retrieval metadata, answers
leave the agent through the `Answer` shapes, and the validator decides whether
that answer is allowed to reach the UI.
