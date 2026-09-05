"""
Thin HTTP client to orchestrator-api.

E6 owns this file. The UI should never call retrieval-api, agent-service,
or answer-validator-api directly — everything goes through the orchestrator.

Set USE_MOCK=True while E4's orchestrator-api isn't ready yet, so you can
build and demo the Gradio UI in isolation. Flip it to False once /ask is live.
"""

import os
import random
import requests

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000")
USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"


# --- Mock responses, one per schema type, so you can exercise every render path ---
_MOCK_RESPONSES = [
    {
        "answer_type": "direct",
        "evidence": [
            {"document_id": "doc_017", "page": 1, "section": "Income Statement"}
        ],
        "params": {"value": "$142.5M"},
    },
    {
        "answer_type": "calculated",
        "evidence": [
            {"document_id": "doc_041", "page": 2, "section": "Operating Expenses"},
            {"document_id": "doc_041", "page": 2, "section": "Operating Expenses"},
        ],
        "params": {"value": 13.4, "formula": "(3875-3410)/3410*100"},
    },
    {
        "answer_type": "multi_span",
        "evidence": [
            {"document_id": "doc_022", "page": 3, "section": "Operating Expenses"}
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

    Raises requests.HTTPError on non-2xx responses when not mocking.
    """
    if USE_MOCK:
        return random.choice(_MOCK_RESPONSES)

    payload = {"question": question}
    if document_id:
        payload["document_id"] = document_id

    resp = requests.post(f"{ORCHESTRATOR_URL}/ask", json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def get_dashboard_data() -> dict:
    """
    Pulls corpus-level stats for the Dashboard tab:
    indexed doc count, doc list, detected tables, recent queries + latency.

    Mocked until orchestrator-api (or eval-service) exposes a real endpoint.
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

    resp = requests.get(f"{ORCHESTRATOR_URL}/dashboard", timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_documents() -> list[dict]:
    """
    Pulls the full indexed document list for the Documents tab:
    per-document id, name, page count, detected tables, and any
    extracted structured values (from doc-processor-api's output).

    Mocked until orchestrator-api exposes a real /documents endpoint.
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

    resp = requests.get(f"{ORCHESTRATOR_URL}/documents", timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_document_detail(document_id: str) -> dict:
    """
    Pulls full detail for a single document — used when the user selects
    a row in the Documents tab table to inspect its extracted content.

    Mocked until orchestrator-api exposes a real endpoint.
    """
    if USE_MOCK:
        docs = {d["document_id"]: d for d in get_documents()}
        doc = docs.get(document_id)
        if not doc:
            return {"error": f"No document found for id '{document_id}'"}
        return doc

    resp = requests.get(f"{ORCHESTRATOR_URL}/documents/{document_id}", timeout=30)
    resp.raise_for_status()
    return resp.json()
