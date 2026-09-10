# Local PDF evaluation workflow

Use Docker Desktop for all seven services and the project `.venv` only for
host-side scripts. Run commands from the repository root.

## Start or restart

```powershell
docker compose up -d --build
docker compose ps
Invoke-RestMethod http://localhost:8006/ready
Invoke-RestMethod http://localhost:8005/health
python scripts/check_stack.py --manifest data/evaluation/manifests/2d95de53424cc9c5.json
```

The first build and first PDF conversion download large dependencies/model
weights. Retrieval must be healthy before agent requests can succeed. Source
`app` folders are mounted read-only; restart the relevant service after code
changes. Rebuild for changed dependencies or shared packages.

The UI is at http://localhost:7860. Qdrant is embedded inside retrieval and
persists in the Docker `ledger_retrieval-data` volume. There is no separate
Qdrant URL or API key. Do not run a second retrieval process against that volume.

## Data and ingestion

The downloaded training archive contains 2,207 PDFs. The 100-question practice
manifest references 101 documents, including 14 absent from training. Fetch
the remaining official splits if needed:

```powershell
python scripts/download_dataset.py --splits dev test
```

Index a single document first, then the corpus (the second command prioritizes
evaluation documents but also indexes the remaining PDFs):

```powershell
python scripts/ingest_corpus.py data --manifest data/evaluation/manifests/2d95de53424cc9c5.json --max-documents 1
python scripts/ingest_corpus.py data --manifest data/evaluation/manifests/2d95de53424cc9c5.json
Invoke-RestMethod http://localhost:8006/ingestion
```

Ingestion is resumable and skips already indexed documents. The PDF filename
stem is the dataset document ID. Annotation answers are never indexed. Do not
evaluate during active ingestion: freeze the searchable corpus first.
Each API-created evaluation run saves `corpus.json` and a corpus fingerprint
in `config.json`. Compare variants only against the same fingerprint; this
snapshot records the indexed PDFs, not a lock preventing later ingestion.

## Evaluation

### Small smoke test (three PDFs, two questions)

For a low-storage check, select only the PDFs needed by the first two practice
questions. This still uses PDF extraction, retrieval, the real agent, validation,
and evaluation; it is not a representative held-out benchmark.

```powershell
python scripts/ingest_corpus.py data --manifest data/evaluation/manifests/2d95de53424cc9c5.json --manifest-items 2 --only-manifest --dry-run
python scripts/ingest_corpus.py data --manifest data/evaluation/manifests/2d95de53424cc9c5.json --manifest-items 2 --only-manifest
python scripts/run_evaluation.py data/evaluation/manifests/2d95de53424cc9c5.json --max-items 2 --variant reranker_on --require-langfuse
```

Ingestion does not remove previously indexed documents. The run's corpus
snapshot records the actual searchable corpus. Selecting fewer PDFs reduces
processing and index storage, but does not shrink the ML dependencies or their
model downloads. Do not start a large rebuild with almost no free disk space.

### Full practice runs

```powershell
python scripts/run_evaluation.py data/evaluation/manifests/2d95de53424cc9c5.json --max-items 1 --require-langfuse
python scripts/run_evaluation.py data/evaluation/manifests/2d95de53424cc9c5.json --variant reranker_on --require-langfuse
python scripts/run_evaluation.py data/evaluation/manifests/2d95de53424cc9c5.json --variant reranker_off --require-langfuse
```

Relative manifest paths resolve from the repository root inside either native
or Docker eval-service. API preflight checks QA readiness, mock mode, and
required indexed document IDs before allocating a run. Missing dependencies
return HTTP 503; missing indexed PDFs return HTTP 409. These checks do not
prove extraction quality or that an LLM provider has sufficient quota.

The practice manifest is suitable for development. Calling it held-out does
not prove it was excluded from tuning; reserve a separate document-disjoint
set before reporting final benchmark performance.

## Interpreting the earlier runs

`20260909T064411Z-d1f94d1f` and `20260909T143409Z-96c7f71e` are historical
infrastructure failures. Their original files are retained. The latter's 5%
EM/F1 was an evaluator defect: missing responses were treated as correct
abstentions on five unanswerable items. Current code gives failed requests zero
answer credit, reports unobserved retrieval as unavailable, and leaves missing
usage totals null. Those old files are not corrected benchmark results.

## Stop safely

```powershell
docker compose stop
```

Keep Docker data volumes and downloaded PDFs to preserve indexing and cached
models across restarts.
