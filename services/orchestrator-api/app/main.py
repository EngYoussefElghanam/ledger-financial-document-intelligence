import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.agent_client import ask_agent
from app.config import DOC_PROCESSOR_URL
from app.http_client import get_client, set_client
from app.validator_client import validate
from schemas.answer import Answer


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = httpx.AsyncClient()
    set_client(client)
    yield
    await client.aclose()


app = FastAPI(title="orchestrator-api", lifespan=lifespan)

_recent_queries: list[dict] = []


class AskRequest(BaseModel):
    question: str
    document_id: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/documents")
async def list_documents() -> list[dict]:
    client = get_client()

    ids_resp = await client.get(f"{DOC_PROCESSOR_URL}/documents", timeout=30)
    ids_resp.raise_for_status()
    document_ids = ids_resp.json()["document_ids"]

    documents = []
    for doc_id in document_ids:
        try:
            detail_resp = await client.get(f"{DOC_PROCESSOR_URL}/documents/{doc_id}", timeout=30)
            detail_resp.raise_for_status()
        except httpx.HTTPError as e:
            print(f"[orchestrator] Skipping document '{doc_id}': {e}")
            continue
        documents.append(_to_ui_summary(detail_resp.json()))

    return documents


@app.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict:
    client = get_client()
    resp = await client.get(f"{DOC_PROCESSOR_URL}/documents/{document_id}", timeout=30)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"No document '{document_id}'")
    resp.raise_for_status()
    return _to_ui_summary(resp.json())


def _to_ui_summary(processed_document: dict) -> dict:
    tables_detected = sum(len(page["tables"]) for page in processed_document["pages"])
    return {
        "document_id": processed_document["document_id"],
        "name": processed_document["source_filename"],
        "pages": processed_document["page_count"],
        "tables_detected": tables_detected,
        "structured_values": {},
    }


def _insufficient_evidence(reason: str) -> dict:
    return {"answer_type": "insufficient_evidence", "evidence": [], "params": {"reason": reason}}


@app.post("/ask", response_model=Answer)
async def ask(request: AskRequest) -> dict:
    start = time.perf_counter()

    try:
        candidate_answer = await ask_agent(request.question, request.document_id)
        validation = await validate(candidate_answer)
    except httpx.HTTPError as e:
        final_answer = _insufficient_evidence(f"Downstream service error: {e}")
    else:
        if validation["valid"]:
            final_answer = candidate_answer
        else:
            final_answer = _insufficient_evidence(f"Answer failed validation: {validation['reason']}")

    latency_ms = round((time.perf_counter() - start) * 1000)
    _recent_queries.append({
        "question": request.question,
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    })

    return final_answer


@app.get("/dashboard")
async def dashboard() -> dict:
    documents = await list_documents()
    return {
        "num_documents": len(documents),
        "documents": documents,
        "recent_queries": _recent_queries[-10:],
    }