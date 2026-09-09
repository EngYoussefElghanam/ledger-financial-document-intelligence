# answer-validator-api

Validates answer JSON against the strict Answer schema (`direct`, `calculated`,
`multi_span`, `insufficient_evidence`) defined in `shared/schemas/answer.py`.

## Setup

    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    pip install -e ../../shared

## Run

    python -m uvicorn app.main:app --reload --port 8004

## Test

    python -m pytest -v

## Endpoints

- `POST /validate_answer` — validates a payload, returns `{"valid": bool, ...}`
- `GET /health`

## Notes

Success logs show only the first evidence citation for brevity (matches the
spec's example format); the full evidence list is always present in the
returned JSON.
