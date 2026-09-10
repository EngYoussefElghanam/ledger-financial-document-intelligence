# LEDGER Windows and TAT-DQA Runbook

This is the manual PowerShell setup. For Docker Desktop using Command Prompt,
follow [the Docker runbook](docker-runbook.md), which requires no dataset
download. Run the commands below only if you choose the native Python setup.

## 1. What the full system does

The live request path is:

```text
TAT-DQA PDF
  -> orchestrator :8006
  -> document processor :8001
  -> retrieval ingestion/Qdrant :8002
  -> corpus manifest

Question from UI :7860
  -> orchestrator :8006
  -> agent :8003
  -> retrieval search :8002
  -> validator :8004
  -> UI
```

Both mock switches must remain disabled for this path.

## 2. Prerequisites

Install these before continuing:

- 64-bit Python 3.11. Avoid Python 3.13 for this project because Docling,
  PyTorch, Qdrant/FastEmbed, and model packages may not all support it.
- Git.
- At least 10 GB of free disk space. The Hugging Face repository is about
  1.51 GB before extraction, and Python packages, model caches, extracted
  PDFs, processed JSON, and Qdrant vectors require additional space.
- A Groq API key. The current agent constructs `ChatGroq` with
  `qwen/qwen3.8-27b`.
- Internet access during installation and the first processor/retrieval
  startup because model weights are downloaded and cached.

The TAT-DQA repository contains 2,758 financial-report documents, 3,067 pages,
and 16,558 questions. Its files are split into train, development, and test
PDF archives plus QA JSON files. See the
[Hugging Face repository](https://huggingface.co/datasets/next-tat/TAT-DQA/tree/main)
and [official dataset description](https://nextplusplus.github.io/TAT-DQA/).

## 3. Open PowerShell at the repository root

The expected folder is:

```text
C:\Users\nadaa\OneDrive\Desktop\mia final\ledger-financial-document-intelligence
```

In PowerShell:

```powershell
Set-Location "C:\Users\nadaa\OneDrive\Desktop\mia final\ledger-financial-document-intelligence"
$repo = (Get-Location).Path
```

Keep paths in quotes because `mia final` contains a space.

## 4. Create and activate Python 3.11 environment

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& ".\.venv\Scripts\Activate.ps1"
python -m pip install --upgrade pip setuptools wheel
```

Confirm that `python --version` reports Python 3.11 before installing the
large dependencies.

## 5. Install the project

Use one environment for the demo and install the local shared schemas last so
all services use this checkout rather than an older remote copy.

```powershell
python -m pip install -r ".\services\doc-processor-api\requirements.txt"
python -m pip install -r ".\services\retrieval-api\requirements.txt"
python -m pip install -r ".\services\agent-service\requirements.txt"
python -m pip install -r ".\services\answer-validator-api\requirements.txt"
python -m pip install -r ".\services\orchestrator-api\requirements.txt"
python -m pip install -r ".\services\ui-service\requirements.txt"
python -m pip install -e ".\shared"
```

The evaluation service is not needed for PDF-to-answer operation. Install its
requirements separately only if you intend to use that service.

The retrieval requirements can take a long time and consume several GB.
PyTorch, Docling, FastEmbed, and reranker dependencies are the largest parts.

## 6. Configure live mode

Create the only environment file at the repository root:

```powershell
Copy-Item ".env.example" ".env"
notepad ".env"
```

Use these values, replacing the key placeholder:

```dotenv
USE_MOCK=false
USE_MOCK_AGENT=false

ORCHESTRATOR_URL=http://localhost:8006
DOC_PROCESSOR_URL=http://localhost:8001
RETRIEVAL_URL=http://localhost:8002
RETRIEVAL_API_URL=http://localhost:8002
AGENT_SERVICE_URL=http://localhost:8003
ANSWER_VALIDATOR_URL=http://localhost:8004

GROQ_API_KEY=replace_with_your_real_groq_key
```

Do not commit `.env`. The configured model is currently listed by Groq as a
preview model. If Groq later retires it, select a supported chat model from
[Groq's model list](https://console.groq.com/docs/models) and update the model
name in `services/agent-service/app/graph.py`.

## 7. Download TAT-DQA manually

Choose one of the following methods. Do not use both.

### Option A: Hugging Face CLI

Install the download client:

```powershell
python -m pip install -U "huggingface_hub[cli]"
```

Download the complete dataset repository:

```powershell
hf download next-tat/TAT-DQA `
  --repo-type dataset `
  --local-dir ".\data\tat-dqa"
```

### Option B: Browser download

Open the
[TAT-DQA file page](https://huggingface.co/datasets/next-tat/TAT-DQA/tree/main)
and save these files under `data\tat-dqa`:

- `tatdqa_docs_train.zip` (about 1.17 GB)
- `tatdqa_docs_dev.zip` (about 156 MB)
- `tatdqa_docs_test.zip` (about 174 MB)
- `tatdqa_dataset_train.json`
- `tatdqa_dataset_dev.json`
- `tatdqa_dataset_test.json`
- `tatdqa_dataset_test_gold.json`

The PDF archives are required for this project's processor and retrieval
pipeline. The JSON files are useful for selecting real benchmark questions
and checking expected answers; they are not ingested into Qdrant.

## 8. Extract the PDF archives

```powershell
New-Item -ItemType Directory -Force ".\data\tat-dqa\docs\train"
New-Item -ItemType Directory -Force ".\data\tat-dqa\docs\dev"
New-Item -ItemType Directory -Force ".\data\tat-dqa\docs\test"

Expand-Archive ".\data\tat-dqa\tatdqa_docs_train.zip" `
  -DestinationPath ".\data\tat-dqa\docs\train" -Force
Expand-Archive ".\data\tat-dqa\tatdqa_docs_dev.zip" `
  -DestinationPath ".\data\tat-dqa\docs\dev" -Force
Expand-Archive ".\data\tat-dqa\tatdqa_docs_test.zip" `
  -DestinationPath ".\data\tat-dqa\docs\test" -Force
```

Confirm that PDFs were extracted:

```powershell
Get-ChildItem ".\data\tat-dqa\docs" -Recurse -Filter "*.pdf" |
  Measure-Object
```

TAT-DQA uses a document UID such as
`11ba155b7577c83fe5f3c4f766039e93`. The corresponding PDF is
`{uid}.pdf`, and the QA JSON refers to the same UID. The corpus ingestion
script preserves the PDF filename stem as LEDGER's `document_id`.

## 9. Start the six services

Open six new PowerShell terminals. In every terminal, set `$repo` and activate
the same environment first:

```powershell
$repo = "C:\Users\nadaa\OneDrive\Desktop\mia final\ledger-financial-document-intelligence"
& "$repo\.venv\Scripts\Activate.ps1"
```

Do not start the UI until the five APIs are healthy.

### Terminal 1: document processor, port 8001

```powershell
Set-Location "$repo\services\doc-processor-api"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

The first Docling conversion may download model files and take several
minutes.

### Terminal 2: retrieval, port 8002

```powershell
Set-Location "$repo\services\retrieval-api"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8002
```

Keep this working directory consistent. Local Qdrant data is stored under
`services\retrieval-api\qdrant_data`. First startup downloads the dense,
sparse, and reranking models and may appear idle for several minutes.

### Terminal 3: answer validator, port 8004

```powershell
Set-Location "$repo\services\answer-validator-api"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8004
```

### Terminal 4: agent, port 8003

```powershell
Set-Location "$repo\services\agent-service"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8003
```

If this terminal reports a missing Groq key, correct the repository-root
`.env` and restart it.

### Terminal 5: orchestrator, port 8006

```powershell
Set-Location "$repo\services\orchestrator-api"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8006
```

### Terminal 6: UI, port 7860

Start this only after the health checks in the next section succeed:

```powershell
Set-Location "$repo\services\ui-service"
python ".\app\main.py"
```

Open `http://localhost:7860`. The header must say **LIVE MODE**. If it says
**MOCK MODE**, stop the UI, correct `.env`, and restart it.

## 10. Check service health

In a seventh PowerShell terminal:

```powershell
Invoke-RestMethod "http://localhost:8001/health"
Invoke-RestMethod "http://localhost:8002/health"
Invoke-RestMethod "http://localhost:8004/health"
Invoke-RestMethod "http://localhost:8003/health"
Invoke-RestMethod "http://localhost:8006/health"
```

The orchestrator response must contain `"mock_agent": false`.

If retrieval does not expose `/health` in your checkout, confirm startup by
opening `http://localhost:8002/docs` and locating `/ingest` and `/search`.

## 11. Ingest one PDF first

Do not begin with all 2,758 documents. Select one PDF from the development
split and copy it into a small staging directory:

```powershell
New-Item -ItemType Directory -Force ".\data\tat-dqa\smoke"
$sample = Get-ChildItem ".\data\tat-dqa\docs\dev" -Recurse -Filter "*.pdf" |
  Select-Object -First 1
Copy-Item $sample.FullName ".\data\tat-dqa\smoke\"
```

Run the resumable corpus command from the repository root:

```powershell
python ".\scripts\ingest_corpus.py" ".\data\tat-dqa\smoke"
```

Expected output contains `INDEXED ... -> <document_uid>`. Re-running the same
command should print `SKIP`, not create a duplicate.

## 12. Inspect ingestion state

```powershell
$state = Invoke-RestMethod "http://localhost:8006/ingestion"
$state.counts
$state.documents | Format-Table document_id,status,failed_stage,total_chunks
```

Lifecycle fields are persisted in `data\corpus-manifest.json`:

- `uploaded_at`: the orchestrator accepted the PDF.
- `processed_at`: Docling produced structured JSON.
- `indexed_at`: retrieval confirmed at least one Qdrant chunk.
- `status = failed`, `failed_stage`, and `error`: a dependency failed.

Only records whose current status is `indexed` appear in `/documents` and in
the UI's indexed-document count.

To resume a document that processed successfully but failed during retrieval:

```powershell
$documentId = "replace_with_document_uid"
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8006/documents/$documentId/resume"
```

If processing itself failed, fix the processor and run `ingest_corpus.py`
again so the PDF can be uploaded and processed again.

## 13. Ask a real TAT-DQA question

Open `tatdqa_dataset_dev.json` in an editor. Choose one entry and note:

- `doc.uid`: use this as the UI document scope.
- A question from its `questions` list.
- Its annotated answer for comparison.

Make sure that `{doc.uid}.pdf` is already indexed. In the UI:

1. Open **Documents** and confirm that UID is listed.
2. Open **Chat**.
3. Enter the UID in the optional `document_id` scope.
4. Ask the matching dataset question.
5. Verify that the response contains evidence from the same UID and a real
   page number.
6. Ask a different question from the same document and confirm that both the
   retrieved evidence and answer change.

You can call the orchestrator without the UI as well:

```powershell
$body = @{
  question = "Replace with a question from tatdqa_dataset_dev.json"
  document_id = "replace_with_doc_uid"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8006/ask" `
  -ContentType "application/json" `
  -Body $body
```

## 14. Run the live PDF-to-answer smoke check

Use two questions whose answers are present in the selected PDF:

```powershell
python ".\scripts\smoke_pdf_to_answer.py" `
  ".\data\tat-dqa\smoke\replace_with_uid.pdf" `
  "First real question from the QA JSON" `
  "Second real question from the QA JSON"
```

The script fails if the orchestrator uses a mock agent, either response has no
evidence, evidence points to another document, or changing the question
returns an identical result.

## 15. Ingest the full corpus

After the single-document smoke test passes, ingest one split at a time:

```powershell
python ".\scripts\ingest_corpus.py" ".\data\tat-dqa\docs\dev"
python ".\scripts\ingest_corpus.py" ".\data\tat-dqa\docs\test"
python ".\scripts\ingest_corpus.py" ".\data\tat-dqa\docs\train"
```

Starting with development and test gives a useful demo corpus sooner. Full
processing is CPU-, memory-, and disk-intensive and can take hours. The script
is resumable: indexed PDFs are skipped and documents that reached processing
retry only retrieval ingestion.

After each split:

```powershell
(Invoke-RestMethod "http://localhost:8006/ingestion").counts
(Invoke-RestMethod "http://localhost:8006/documents").Count
```

The `/documents` count is the searchable count. Do not use the number of JSON
files under the processor's `data\processed` directory as an indexing count.

## 16. Common failures

### `No module named schemas`

From the repository root with the environment active:

```powershell
python -m pip install -e ".\shared"
```

Then restart the failed service.

### `Form data requires python-multipart`

```powershell
python -m pip install python-multipart
```

Restart the orchestrator or processor.

### Agent returns HTTP 500 or orchestrator returns HTTP 502

Check, in order:

1. `GROQ_API_KEY` exists in the root `.env` and has no placeholder text.
2. Agent port 8003 is running.
3. Retrieval port 8002 is running.
4. `RETRIEVAL_API_URL` is `http://localhost:8002`.
5. The configured Groq model is still available to your account.

### Retrieval starts slowly

Wait for the embedding and reranking models to finish downloading. Keep the
terminal open. Subsequent starts should use the local model cache.

### Qdrant lock or storage error

Ensure only one retrieval process uses
`services\retrieval-api\qdrant_data`. Always launch retrieval from its service
directory so it reopens the same database.

### Processing is slow or memory usage is high

This is expected with Docling and thousands of PDFs. Validate one PDF first,
ingest split by split, and stop other memory-heavy applications.

### A document is processed but absent from the UI

Check `/ingestion`. This is intentional when retrieval did not confirm
indexing. If `processed_at` exists, call the resume endpoint after fixing
retrieval.

## 17. Normal shutdown and restart

Press `Ctrl+C` once in each service terminal. Do not delete these directories
if you want to resume later:

- `data\corpus-manifest.json`
- processor upload and processed-data directories
- `services\retrieval-api\qdrant_data`

On restart, use the same working directories and ports, run all health checks,
and invoke `ingest_corpus.py` again. Previously indexed PDFs will be skipped.
