# Retrieval API

The Retrieval API indexes processed financial documents and returns the most relevant text and table chunks for a query. It uses hybrid retrieval in Qdrant:

- Dense embeddings for semantic similarity
- BM25 sparse embeddings for keyword matching
- Reciprocal rank fusion followed by a cross-encoder reranker

The API is implemented with FastAPI and listens on port `8000` by default.

## Run locally

From the repository root:

```powershell
pip install -r services/retrieval-api/requirements.txt
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --app-dir services/retrieval-api --host 0.0.0.0 --port 8000
```

The embedding and reranking models are downloaded by their libraries on first use. Open the interactive API documentation at <http://localhost:8000/docs>.

## Run with Docker

Build from the repository root because the Dockerfile copies files from both `services/` and `shared/`:

```powershell
docker build -t retrieval-api -f services/retrieval-api/Dockerfile .
docker run --rm -p 8000:8000 retrieval-api
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

Searches the indexed chunks. `document_id` is optional and restricts results to one document. `limit` defaults to `5`; the service fetches additional candidates before reranking.

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

## Storage and configuration

The current implementation uses `QdrantClient(":memory:")`. Indexed data is held in process memory and is lost whenever the service restarts. The collection name is `financials`.

The service currently has no authentication, persistent Qdrant configuration, or environment-variable settings. We should add those before exposing it outside a trusted development environment.