# UI Service

The UI Service is the Gradio front end for LEDGER. It gives the user a
corpus-wide chat, a dashboard of indexed documents, and a document inspector.
It never calls `retrieval-api`, `agent-service`, or `answer-validator-api`
directly — every request goes through `orchestrator-api`.

The service is implemented with Gradio and listens on port `7860` by default
(or the next free port if 7860 is taken).

## Run locally

From the repository root:

```powershell
pip install -r services/ui-service/requirements.txt
python services/ui-service/app/main.py
```

Open <http://localhost:7860>.

## Run with Docker

Build from the repository root:

```powershell
docker build -t ui-service -f services/ui-service/Dockerfile .
docker run --rm -p 7860:7860 --env-file services/ui-service/.env ui-service
```

## Pages

### Chat

Corpus-wide question answering. Sends the question (and an optional
`document_id` to scope the search) to `orchestrator-api`, then renders
whichever of the 4 answer types comes back, always with its cited evidence.

Example request sent to `orchestrator-api`:

```json
{
  "question": "What was the operating income in 2020?",
  "document_id": null
}
```

Example response consumed and rendered:

```json
{
  "answer_type": "direct",
  "evidence": [
    { "document_id": "doc_017", "page": 1, "section": "Income Statement" }
  ],
  "params": { "value": "$142.5M" }
}
```

All 4 answer types are handled in `app/components/format_answer.py`:
`direct`, `calculated`, `multi_span`, `insufficient_evidence`.

### Dashboard

Corpus-level stats: number of indexed documents, the document list, and
recent queries with their latency.

### Documents

Lists every indexed document (id, name, pages, tables detected). Selecting
a document — by clicking its row or entering its `document_id` — shows its
extracted structured values.

## Storage and configuration

The service holds no data of its own; everything is fetched from
`orchestrator-api` on each request. Configuration lives in `.env`:

| Variable | Purpose |
|---|---|
| `ORCHESTRATOR_URL` | Base URL of `orchestrator-api` |
| `USE_MOCK` | `true` = serve built-in mock responses, no orchestrator needed. `false` = call the real API |

The service currently runs entirely on **mocked** responses
(`USE_MOCK=true`) since `orchestrator-api`'s `/ask`, `/dashboard`, and
`/documents` endpoints aren't live yet. Switch `USE_MOCK=false` once they
are, and confirm the real response shape matches the schema above.

We should add real error handling for a down/slow orchestrator, and a way
to open the cited PDF page directly from an evidence citation, before
relying on this in the final demo.