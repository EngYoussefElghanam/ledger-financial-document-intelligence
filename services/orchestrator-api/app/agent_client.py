"""
Client for agent-service (the LangGraph reasoning "brain").

USE_MOCK_AGENT lets orchestrator-api be tested without a running
agent-service, flip it to false once agent-service is available.
"""

import os
import random

from app.config import AGENT_SERVICE_URL
from app.http_client import get_client

USE_MOCK_AGENT = os.getenv("USE_MOCK_AGENT", "true").lower() == "true"

_MOCK_ANSWERS = [
    {
        "answer_type": "direct",
        "evidence": [{"document_id": "doc_017", "page": 1, "section": "Income Statement"}],
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
        "answer_type": "insufficient_evidence",
        "evidence": [],
        "params": {"reason": "No document in the indexed corpus reports restructuring expenses."},
    },
]


async def ask_agent(question: str, document_id: str | None = None) -> dict:
    if USE_MOCK_AGENT:
        return random.choice(_MOCK_ANSWERS)

    client = get_client()
    resp = await client.post(
        f"{AGENT_SERVICE_URL}/answer",
        json={"question": question, "document_id": document_id},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()