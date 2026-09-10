"""
Thin HTTP client to orchestrator-api.

E6 owns this file. The UI should never call retrieval-api, agent-service,
or answer-validator-api directly — everything goes through the orchestrator.

USE_MOCK=true falls back to canned responses (for local UI dev without
orchestrator-api running). Default is false now that orchestrator-api
(port 8006) is live and tested.
"""

import os
import random
import requests

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8006")
USE_MOCK = os.getenv("USE_MOCK", "false").lower() == "true"


def runtime_status() -> dict:
    """Expose the active backend mode for the UI status banner."""
    return {"mock": USE_MOCK, "orchestrator_url": ORCHESTRATOR_URL}


class OrchestratorError(Exception):
    """Raised for any failure talking to orchestrator-api — connection
    refused, timeout, bad status code, or a response that doesn't match
    the expected shape. Callers catch this and show a clean message
    instead of letting a raw exception hit the Gradio UI."""


def _get(path: str, timeout: int) -> dict | list:
    try:
        resp = requests.get(f"{ORCHESTRATOR_URL}{path}", timeout=timeout)
    except requests.exceptions.ConnectionError as e:
        raise OrchestratorError(
            f"Can't reach orchestrator-api at {ORCHESTRATOR_URL}. "
            f"Is it running? ({e})"
        ) from e
    except requests.exceptions.Timeout as e:
        raise OrchestratorError(
            f"orchestrator-api didn't respond within {timeout}s "
            f"(request to {path})."
        ) from e

    if not resp.ok:
        raise OrchestratorError(
            f"orchestrator-api returned {resp.status_code} for {path}: "
            f"{resp.text[:200]}"
        )

    try:
        return resp.json()
    except ValueError as e:
        raise OrchestratorError(
            f"orchestrator-api returned non-JSON for {path}."
        ) from e


def _post(path: str, payload: dict, timeout: int) -> dict:
    try:
        resp = requests.post(f"{ORCHESTRATOR_URL}{path}", json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError as e:
        raise OrchestratorError(
            f"Can't reach orchestrator-api at {ORCHESTRATOR_URL}. "
            f"Is it running? ({e})"
        ) from e
    except requests.exceptions.Timeout as e:
        raise OrchestratorError(
            f"orchestrator-api didn't respond within {timeout}s "
            f"(request to {path}). It may be waiting on agent-service, "
            f"which calls an LLM and can be slow."
        ) from e

    if not resp.ok:
        raise OrchestratorError(
            f"orchestrator-api returned {resp.status_code} for {path}: "
            f"{resp.text[:200]}"
        )

    try:
        return resp.json()
    except ValueError as e:
        raise OrchestratorError(
            f"orchestrator-api returned non-JSON for {path}."
        ) from e


def _validate_answer_shape(data: dict) -> dict:
    """orchestrator-api's /ask always returns one of the 4 known
    answer_type schemas (it substitutes insufficient_evidence itself if
    agent's answer fails validation) — but we still guard here in case a
    future contract change slips through, rather than letting
    format_answer.py fail on an unexpected shape."""
    if not isinstance(data, dict) or "answer_type" not in data:
        raise OrchestratorError(
            f"orchestrator-api's /ask response is missing 'answer_type': {data}"
        )
    return data


# --- Mock responses, one per schema type, used only when USE_MOCK=true ---
_MOCK_RESPONSES = [
    {
        "answer_type": "direct",
        "evidence": [
            {
                "document_id": "doc_017",
                "filename": "cts-corporation_2019.pdf",
                "page": 1,
                "section": "Income Statement",
                "quote": "Operating income was $142.5 million.",
            }
        ],
        "params": {"value": "$142.5M"},
    },
    {
        "answer_type": "calculated",
        "evidence": [
            {"document_id": "doc_041", "filename": "jabil-circuit-inc_2019.pdf", "page": 2, "section": "Operating Expenses", "quote": "Operating expenses were 3,875 and 3,410."},
            {"document_id": "doc_041", "filename": "jabil-circuit-inc_2019.pdf", "page": 2, "section": "Operating Expenses", "quote": "Operating expenses were 3,875 and 3,410."},
        ],
        "params": {"value": 13.4, "formula": "(3875-3410)/3410*100"},
    },
    {
        "answer_type": "multi_span",
        "evidence": [
            {"document_id": "doc_022", "filename": "black-knight-financial-services-inc_2019.pdf", "page": 3, "section": "Operating Expenses", "quote": "Marketing, R&D and logistics were the principal categories."}
        ],
        "params": {"values": ["Marketing", "R&D", "Logistics"]},
    },
    {
        "answer_type": "insufficient_evidence",
        "evidence": [],
        "params": {"reason": "No document in the indexed corpus reports restructuring expenses."},
    },
]


def ask_question(question: str, document_id: str | None = None) -> dict:
    """
    Send a question to the orchestrator and return the schema-compliant
    answer dict: {answer_type, evidence, params}.

    Raises OrchestratorError on any failure (connection, timeout, bad
    status, malformed response) — callers should catch this, never
    requests.RequestException directly.
    """
    if USE_MOCK:
        return random.choice(_MOCK_RESPONSES)

    payload = {"question": question}
    if document_id:
        payload["document_id"] = document_id

    # 60s: agent-service calls an LLM, per its own timeout budget
    data = _post("/ask", payload, timeout=60)
    return _validate_answer_shape(data)


def get_dashboard_data() -> dict:
    """
    Pulls corpus-level stats for the Dashboard tab:
    indexed doc count, doc list, recent queries + latency + timestamp.

    Note: orchestrator-api's /dashboard internally calls /documents,
    which fetches every document one-by-one from doc-processor-api
    (2,758 documents in the full corpus as of doc-processor-api's
    latest update) — this call can be slow. Give it a generous timeout
    and show a loading state in the UI rather than a short timeout that
    fails on a corpus this size.
    """
    if USE_MOCK:
        return {
            "num_documents": 2758,
            "documents": [
                {"document_id": "doc_017", "name": "cts-corporation_2019.pdf", "pages": 1},
                {"document_id": "doc_041", "name": "jabil-circuit-inc_2019.pdf", "pages": 1},
            ],
            "recent_queries": [
                {"question": "What was the operating income in 2020?", "latency_ms": 842, "timestamp": "2026-09-05 14:02:11"},
                {"question": "Compare finished goods between CTS and Jabil", "latency_ms": 1210, "timestamp": "2026-09-05 14:05:47"},
            ],
        }

    return _get("/dashboard", timeout=120)


def get_documents() -> list[dict]:
    """
    Pulls the full indexed document list for the Documents tab.

    Same slow-endpoint caveat as get_dashboard_data(): orchestrator-api
    fetches each document individually from doc-processor-api, so this
    can take a while against the full corpus.
    """
    if USE_MOCK:
        return [
            {
                "document_id": "doc_017",
                "name": "cts-corporation_2019.pdf",
                "pages": 1,
                "tables_detected": 2,
                "structured_values": {"Finished Goods (2019)": "9,447"},
            },
            {
                "document_id": "doc_041",
                "name": "jabil-circuit-inc_2019.pdf",
                "pages": 1,
                "tables_detected": 3,
                "structured_values": {"Finished Goods (2019)": "314,258"},
            },
            {
                "document_id": "doc_022",
                "name": "black-knight-financial-services-inc_2019.pdf",
                "pages": 1,
                "tables_detected": 1,
                "structured_values": {},
            },
        ]

    return _get("/documents", timeout=120)


def get_document_detail(document_id: str) -> dict:
    """
    Pulls full detail for a single document — used when the user selects
    a row in the Documents tab table to inspect its extracted content.
    """
    if USE_MOCK:
        docs = {d["document_id"]: d for d in get_documents()}
        doc = docs.get(document_id)
        if not doc:
            return {"error": f"No document found for id '{document_id}'"}
        return doc

    return _get(f"/documents/{document_id}", timeout=30)
