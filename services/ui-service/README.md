# ui-service

Gradio front end for LEDGER. Owns the chat, dashboard, and documents views;
talks to `orchestrator-api` for everything else.

## Structure

```
ui-service/
├── Dockerfile
├── requirements.txt
├── .env.example
└── app/
    ├── main.py           # entrypoint — builds the Gradio Blocks app
    ├── client.py          # HTTP client to orchestrator-api (mockable)
    └── components/
        ├── chat_tab.py
        ├── dashboard_tab.py
        ├── documents_tab.py
        └── format_answer.py   # renders the 4 answer_type schemas
```

## Run locally (without Docker)

```bash
cd services/ui-service
pip install -r requirements.txt
cp .env.example .env
cd app
python main.py
```

Opens on `http://localhost:7860`.

## Run with Docker

```bash
docker build -t ledger-ui-service .
docker run -p 7860:7860 --env-file .env ledger-ui-service
```

## Config (`.env`)

| Variable | Purpose |
|---|---|
| `ORCHESTRATOR_URL` | Base URL of orchestrator-api |
| `USE_MOCK` | `true` = use built-in mock responses (no orchestrator needed), `false` = hit the real API |

## Current status

- Chat, Dashboard, and Documents tabs are functional against **mocked** data.
- `answer-validator-api`'s 4 answer types (`direct`, `calculated`, `multi_span`,
  `insufficient_evidence`) are all handled in `components/format_answer.py`.
- **Not yet done:** live connection to `orchestrator-api` (`/ask`, `/dashboard`,
  `/documents` endpoints — switch `USE_MOCK=false` once these exist and match
  the expected response shape below), opening the cited PDF page from an
  evidence citation, richer error handling.

### Expected `/ask` response shape (from `shared/schemas/`)

```json
{
  "answer_type": "direct | calculated | multi_span | insufficient_evidence",
  "evidence": [ { "document_id": "...", "page": 0, "section": "..." } ],
  "params": { ... }
}
```
