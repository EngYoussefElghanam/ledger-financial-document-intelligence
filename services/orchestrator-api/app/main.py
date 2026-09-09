import httpx
from fastapi import FastAPI, HTTPException

from app.config import DOC_PROCESSOR_URL

import time
from datetime import datetime, timezone

from pydantic import BaseModel

from app.agent_client import ask_agent
from app.validator_client import validate

app = FastAPI(title="orchestrator-api")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/documents")
async def list_documents() -> list[dict]:
    async with httpx.AsyncClient() as client:
        # Step 1: get the list of ids from doc-processor-api
        ids_resp = await client.get(f"{DOC_PROCESSOR_URL}/documents", timeout=30)
        ids_resp.raise_for_status()
        document_ids = ids_resp.json()["document_ids"]

        # Step 2: fetch full detail per document, so we can compute
        # UI-facing fields (name, tables_detected) that don't exist
        # in the plain id list.
        documents = []

        # this does the requests one after another which is not optimal performance
        # can later be improved using techniques such as: asyncio.gather(...) or preferably change the architecture so we don't need thousands of individual requests.
        for doc_id in document_ids:
            detail_resp = await client.get(f"{DOC_PROCESSOR_URL}/documents/{doc_id}", timeout=30)
            detail_resp.raise_for_status()
            documents.append(_to_ui_summary(detail_resp.json()))

        return documents


@app.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{DOC_PROCESSOR_URL}/documents/{document_id}", timeout=30)
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"No document '{document_id}'")
        resp.raise_for_status()
        return _to_ui_summary(resp.json())


def _to_ui_summary(processed_document: dict) -> dict:
    """Reshape a full ProcessedDocument (doc-processor-api's format) into
    the smaller summary shape ui-service's client.py expects."""
    tables_detected = sum(len(page["tables"]) for page in processed_document["pages"])
    return {
        "document_id": processed_document["document_id"],
        "name": processed_document["source_filename"],
        "pages": processed_document["page_count"],
        "tables_detected": tables_detected,
        "structured_values": {},  # nothing extracts this yet, either doc-processor-api needs to extract it, or it's actually eval-service's/agent-service's job later.
    }


# In-memory log of recent questions, for the /dashboard endpoint.
# Resets on every server restart which is fine for a demo, not meant to be
# durable storage (that's arguably eval-service's job long-term).
_recent_queries: list[dict] = []


class AskRequest(BaseModel):
    question: str
    document_id: str | None = None


@app.post("/ask")
async def ask(request: AskRequest) -> dict:
    start = time.perf_counter()

    candidate_answer = await ask_agent(request.question, request.document_id)
    validation = await validate(candidate_answer)

    if validation["valid"]:
        final_answer = candidate_answer
    else:
        # Validation failed: don't forward a broken/unvalidated answer to
        # the user. Substitute a schema-compliant insufficient_evidence
        # answer instead, per the spec's "never hallucinate" philosophy.
        final_answer = {
            "answer_type": "insufficient_evidence",
            "evidence": [],
            "params": {"reason": f"Answer failed validation: {validation['reason']}"},
        }

    latency_ms = round((time.perf_counter() - start) * 1000)
    _recent_queries.append({
        "question": request.question,
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    })

    return final_answer


@app.get("/dashboard")
async def dashboard() -> dict:
    documents = await list_documents()  # reuses the endpoint function you already wrote
    return {
        "num_documents": len(documents),
        "documents": documents,
        "recent_queries": _recent_queries[-10:],  # last 10 only, keep it small
    }
