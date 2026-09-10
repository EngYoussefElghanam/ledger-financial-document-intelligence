# Retrieval API

The Retrieval API indexes processed financial documents and returns the most relevant text and table chunks for a query. It uses hybrid retrieval in Qdrant:

- Dense embeddings for semantic similarity
- BM25 sparse embeddings for keyword matching
- Reciprocal rank fusion followed by a cross-encoder reranker

The API is implemented with FastAPI and uses port `8002` in the LEDGER stack.

## Run locally

From the repository root:

```powershell
pip install -r services/retrieval-api/requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --app-dir services/retrieval-api --host 0.0.0.0 --port 8002
```

The embedding and reranking models are downloaded by their libraries on first use. Open the interactive API documentation at <http://localhost:8002/docs>.

## Run with Docker

Build from the repository root because the Dockerfile copies files from both `services/` and `shared/`:

```powershell
docker build -t retrieval-api -f services/retrieval-api/Dockerfile .
docker run --rm -p 8002:8002 retrieval-api
```

## Endpoints

### `POST /ingest`

Chunks and indexes a processed document. Text blocks are grouped with their section headings. Tables are flattened into searchable text while retaining document, page, section, and content type metadata.

Example request:

```json
{
	"document_id": "annual-report-2024",
	"source_filename": "annual-report-2024.pdf",
	"page_count": 1,
	"pages": [
		{
			"page_number": 1,
			"blocks": [
				{
					"block_id": "block-1",
					"content_type": "paragraph",
					"text": "Revenue increased by 12 percent in 2024.",
					"section": "Financial Highlights",
					"bbox": [72, 100, 500, 130]
				}
			],
			"tables": []
		}
	]
}
```

Example response:

```json
{
	"status": "success",
	"total_chunks": 1
}
```

### `POST /search`

Searches the indexed chunks. `document_id`, `content_type`, and `section` are
optional pre-retrieval filters. `limit` defaults to `5`; the service fetches
additional candidates before reranking. Evaluation requests can set
`rerank=false` and `include_diagnostics=true` to capture the controlled baseline
and pre-reranker candidate ranks.

Example request:

```json
{
	"query": "What was revenue in 2024?",
	"document_id": "annual-report-2024",
	"limit": 5
}
```

Example response:

```json
{
	"results": [
		{
			"chunk_id": "block-1",
			"rank": 1,
			"score": 4.21,
			"text": "Section: Financial Highlights\nContent: Revenue increased by 12 percent in 2024.",
			"metadata": {
				"document_id": "annual-report-2024",
				"page_number": 1,
				"section": "Financial Highlights",
				"type": "text"
			}
		}
	]
}
```

If no matching chunks are found, the endpoint returns `{ "results": [] }`.

### `POST /filter`

Returns chunks by exact metadata without vector search. `document_id` is
required; `type`, `section`, and `limit` are optional. Agent-service uses this
route when a question targets a known document or section.

```json
{
	"document_id": "annual-report-2024",
	"type": "table",
	"section": "Financial Highlights",
	"limit": 50
}
```

### Bulk indexing processed JSON

From the repository root, run `python services/retrieval-api/app/indexer.py` to
submit every `data/processed/*.json` file. Override `PROCESSED_DIR` or
`RETRIEVAL_API_URL` when the files or service use different locations.

## Storage and configuration

The current implementation uses local Qdrant storage at `./qdrant_data`; Compose
mounts it as a persistent volume. The collection name is `financials`.

The service currently has no authentication, persistent Qdrant configuration, or environment-variable settings. We should add those before exposing it outside a trusted development environment.
