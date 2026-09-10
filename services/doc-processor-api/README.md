# doc-processor-api

The Document Processing service for **Project LEDGER**. Takes raw financial-report PDFs and turns them into structured, machine-readable data — text, tables, section headings, page numbers, and bounding boxes — using [docling](https://github.com/DS4SD/docling)'s deep-learning layout model and TableFormer for table structure recognition.

This is the **only** service in LEDGER that touches raw PDFs. Every other service (retrieval-api, agent-service, etc.) works exclusively off this service's structured JSON output.

## What this service does *not* do

- It does not chunk the output for retrieval — it produces section-tagged, table-aware structured data that *enables* chunking; `retrieval-api` owns the actual chunking logic.
- It does not use the TAT-DQA dataset's own pre-parsed reference JSON as input anywhere in the pipeline — only raw PDFs are processed, per the project's dataset rules. The reference JSON is only used as ground truth during manual validation (see below).

## Architecture

```
app/
  main.py         - FastAPI endpoints
  processor.py    - the docling wrapper (process_pdf)
  warmup.py       - pre-downloads docling model weights at Docker build time
tests/
  test_main.py       - integration tests against the FastAPI layer
  test_processor.py  - regression test against a known sample PDF
  fixtures/           - sample PDFs used by tests
batch_eval.py     - structural sanity-checker for running against a directory of PDFs
Dockerfile        - optional; see "Docker" below
```

The output schema (`ProcessedDocument`) lives in `shared/schemas/` at the repo root, not in this service — it's the shared contract with `retrieval-api`. Import it as:

```python
from schemas import ProcessedDocument, Block, Table, Page
```

not `shared.schemas` — see the repo root `shared/README` or ask in the team channel if this doesn't resolve; it requires `pip install -e shared/` once per environment.

## Output schema

Every processed document is a `ProcessedDocument`:

| Field | Type | Notes |
|---|---|---|
| `document_id` | str | Defaults to the PDF's filename stem |
| `source_filename` | str | |
| `page_count` | int | |
| `pages` | `Page[]` | |

Each `Page` has `blocks: Block[]` and `tables: Table[]`. Every `Block`/`Table` carries `document_id`-adjacent metadata directly on the item:

- `content_type`: `heading` / `paragraph` / `list_item` / `caption` / `table`
- `section`: the nearest real heading above this item (tracked across page boundaries, not reset per page)
- `bbox`: `[x0, y0, x1, y1]`

`Table` additionally has `num_rows`, `num_cols`, and `rows` (a 2D array of strings, header row included).

Full JSON Schema is auto-generated at `shared/schemas/document.schema.json` via `export_schema.py`.

## Running locally

**Requires Python 3.11 or 3.12.** Python 3.14 is not yet reliably supported by PyTorch/RapidOCR's compiled native extensions and can cause a hard segmentation fault on certain PDFs — see Known Limitations #3.

```bash
# one-time: install the shared schema package
pip install -e ../../shared

# install service dependencies
pip install -r requirements.txt

# run
uvicorn app.main:app --reload
```

Interactive API docs: `http://localhost:8001/docs`

## Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `POST /process` | Upload one PDF, get back its `ProcessedDocument`, persisted to `data/processed/{document_id}.json` |
| `POST /process_batch` | Process every PDF in a given directory; tolerates individual file failures without aborting the run |
| `GET /documents/{document_id}` | Read back a previously processed document (no reprocessing) |
| `GET /documents` | List all currently-indexed document IDs |

## Testing

```bash
pytest tests/
```

8/8 tests passing — covers the full HTTP flow (`test_main.py`) and a locked-in regression check against a known sample PDF's structure, including the documented row-split limitation below (`test_processor.py`).

## Validation against real data

Structural correctness was validated in two passes using `batch_eval.py`, a script that runs `process_pdf()` across a directory and flags hard failures, zero-table documents, empty pages, and tables where `num_rows`/`num_cols` don't match the actual row/column count.

```bash
python batch_eval.py /path/to/pdf/directory
```

**Pass 1 — 50-document sample:** 50/50 succeeded, 0 flags raised across all checks, ~4.26s/document average.

**Pass 2 — full 2,207-document TAT-DQA training corpus:**

| Metric | Result |
|---|---|
| Documents processed | 2,192 / 2,207 |
| Hard failures | 0 |
| Empty pages | 0 |
| Miscounted tables (num_rows/num_cols mismatch) | 0 |
| Avg time per document | 7.24s |
| Flagged as zero-table | 8 (manually reviewed: all correct — genuinely tableless prose pages) |
| Flagged as suspicious table (≤1 row/col) | 2 (manually reviewed: both false positives — see Known Limitations) |

## Known limitations / failure analysis

**1. Fixed — table row/column counts were off by one.**
`num_rows`/`num_cols` were originally computed from pandas' `df.shape`, which excludes the header row that gets prepended separately to `rows`. Fixed to count `len(rows)` directly. Verified with a regression test and confirmed across both the 50- and 2,191-document validation runs (0 miscounted tables in either).

**2. Documented, not patched — inconsistent row-splitting on wrapped table cells.**
When a table cell's text wraps across two lines, docling's TableFormer occasionally splits it into two separate rows instead of one (e.g. a company name like "Marine Exhaust Technology Ltd." becoming two rows). Confirmed on 2 of ~11+ similar wrapped-cell cases checked across multiple real documents; a visually identical wrapped cell in other documents did *not* split. Given the inconsistency, a corrective heuristic (e.g. merging mostly-blank rows) was deliberately avoided, since it risks corrupting other legitimately sparse rows elsewhere in the corpus. Root cause: table structure recognition (TableFormer), not this service's mapping logic.

**3. Resolved — one document appeared to cause a hard crash; root cause was the local Python version, not the document.**
Document `2c52b143491fd26153a2159c6f2c1ab1` triggered a segmentation fault when processed under a local **Python 3.14** environment, reproduced consistently in an isolated, fresh-process run. Since a segfault cannot be caught by Python exception handling, it initially had to be excluded from the corpus (quarantined) to let the full batch run complete. Root-caused by re-running the identical, unmodified file under **Python 3.12**: it processed successfully with no errors. Python 3.14 was released very recently and PyTorch/RapidOCR's compiled native extensions don't yet reliably support it. The Docker image was never affected, since it explicitly pins `python:3.11-slim`. **Resolution:** run local development on Python 3.11–3.12, not 3.14; the document has been restored to the corpus.

**4. Non-issue — automated "suspicious table" flag has false positives.**
`batch_eval.py` flags any table with ≤1 row or column as suspicious. Manual review of both flagged cases in the full run showed correct extractions of genuinely small tables: a 1-column sidebar navigation menu (not real financial data) and a genuinely single-column source table (a definition/formula list with no numeric column in the original PDF). No real data loss found among flagged cases.

## Docker

Docker is a bonus per the project spec, not a requirement, but this service is fully containerized and verified working.

The Dockerfile pins Python 3.11 explicitly (side-stepping the Python 3.14 issue above entirely) and installs `torch`/`torchvision` as an exact matched pair via a pip constraints file — installing them separately or from mismatched sources causes a native `operator torchvision::nms does not exist` crash at runtime. `app/warmup.py` runs a real, self-contained one-page PDF conversion at build time (not just constructing `DocumentConverter()`, which does *not* trigger RapidOCR's lazy model downloads) so the resulting image already has all model weights cached — no live downloads on a container's first real request.

The Dockerfile lives inside this service's own folder (not the repo root) to avoid colliding with other services' Dockerfiles; the build context is still the repo root.

```bash
# from the repo root
docker build -t doc-processor-api -f services/doc-processor-api/Dockerfile .
docker run -p 8001:8001 doc-processor-api
```

To build with GPU-enabled torch instead of the CPU-only default (requires an NVIDIA GPU + NVIDIA Container Toolkit on the host, and `docker run --gpus all`):
```bash
docker build -t doc-processor-api -f services/doc-processor-api/Dockerfile --build-arg TORCH_VARIANT=cuda .
```

## Status / what's left

- [x] Shared schema, merged to `main`
- [x] `processor.py` (docling wrapper)
- [x] FastAPI endpoints
- [x] Tests (8/8 passing)
- [x] Full corpus structural validation (2,192/2,207 documents)
- [x] Docker containerization, built and verified working
- [ ] Merge `feature/doc-processor` into `main`
