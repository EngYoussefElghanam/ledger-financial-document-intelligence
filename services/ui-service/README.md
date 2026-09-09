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
| `ORCHESTRATOR_URL` | Base URL of `orchestrator-api` (port `8006` — moved from `8000` after a collision with `retrieval-api`, see PR #14) |
| `USE_MOCK` | `true` = serve built-in mock responses, no orchestrator needed. `false` (default) = call the real API |
| `PDF_BASE_URL` | Optional. When set, evidence citations become clickable links that open the source PDF at the cited page (`{PDF_BASE_URL}/{document_id}.pdf#page={page}`). Left empty, evidence stays plain text — no code change needed either way. |

`orchestrator-api`'s `/ask`, `/dashboard`, and `/documents` are live and
tested (PR #10) — `USE_MOCK=false` is now the default. Its response
shapes were checked directly against this service's client code:
`/documents` already returns exactly `{document_id, name, pages,
tables_detected, structured_values}`, and `/dashboard`'s `recent_queries`
already include `timestamp`.

`client.py` raises a single `OrchestratorError` for every failure mode
(connection refused, timeout, non-2xx status, malformed JSON) — every
page catches it and shows a clear message instead of crashing. Verified
against a live connection-refused case, a real HTTP 500, and a real
timeout.

`/dashboard` and `/documents` proxy through `doc-processor-api` one
document at a time (not parallelized yet, per orchestrator-api's own
code comments) — slow against the full 2,758-document corpus. Both tabs
show a "Loading…" state and use a generous timeout rather than failing
on a large corpus.

Known gap carried over from `orchestrator-api`: `structured_values` in
`/documents` is currently always empty — nothing in the pipeline
extracts named financial figures yet (open question for the team, per
Shams's PR notes).

Still to add if there's time before the demo:
- Tests
- Parallelizing `/documents` fetches (that's orchestrator-api's fix to make, not this service's)
