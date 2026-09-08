# orchestrator-api

Central router for LEDGER. Routes questions to agent-service, validates
the answer via answer-validator-api before returning it, and proxies
document listings from doc-processor-api into the shape ui-service expects.

## Setup

    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    pip install -e ..\..\shared

## Run

    python -m uvicorn app.main:app --reload --port 8000

## Test

    python -m pytest -v

## Endpoints

- `POST /ask` — `{question, document_id?}` -> schema-compliant answer dict
- `GET /documents` / `GET /documents/{id}` — proxied + reshaped from doc-processor-api
- `GET /dashboard` — document count + recent query log
- `GET /health`

## Config (env vars, see app/config.py)

DOC_PROCESSOR_URL, RETRIEVAL_URL, AGENT_SERVICE_URL, ANSWER_VALIDATOR_URL

## Mocking

USE_MOCK_AGENT=true (default) returns a random canned answer instead of
calling agent-service, since it doesn't exist yet. Set to false once a
real agent-service is running on AGENT_SERVICE_URL.

## Design note: invalid answers

If answer-validator-api rejects the agent's answer, orchestrator does NOT
forward it. It substitutes a schema-compliant `insufficient_evidence`
answer instead, with the validator's rejection reason attached — this
keeps ui-service's rendering logic simple (only ever 4 known answer
types) and matches the spec's "never hallucinate" philosophy.
