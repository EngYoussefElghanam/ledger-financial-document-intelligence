"""
Client for agent-service (the LangGraph reasoning "brain").

agent-service doesn't exist yet, so USE_MOCK_AGENT
lets orchestrator-api be built and tested end-to-end without being
blocked. Flip it to false once a real agent-service is running -
the real-call code path is already written and ready to go.
"""

import os
import random

import httpx

from app.config import AGENT_SERVICE_URL

USE_MOCK_AGENT = os.getenv("USE_MOCK_AGENT", "true").lower() == "true"

# One mock per answer_type, so /ask exercises every downstream path
# (including a deliberately invalid one, to prove the validator actually
# rejects bad input rather than rubber-stamping everything).
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

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AGENT_SERVICE_URL}/answer",
            json={"question": question, "document_id": document_id},
            timeout=60,  # agent calls an LLM - give it real room to think
        )
        resp.raise_for_status()
        return resp.json()