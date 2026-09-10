import hashlib
import re
import uuid
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Response, UploadFile
from pydantic import BaseModel
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse

from app.agent_client import AgentDependencyError, ask_agent
from app.config import (
    AGENT_SERVICE_URL,
    ANSWER_VALIDATOR_URL,
    DOC_PROCESSOR_URL,
    RETRIEVAL_URL,
    USE_MOCK_AGENT,
)
from app.corpus_manifest import get_document as get_manifest_document
from app.corpus_manifest import list_documents as list_manifest_documents
from app.corpus_manifest import update_document
from app.http_client import get_client, set_client
from app.validator_client import validate
from ledger_observability import observation
from schemas.answer import Answer


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = httpx.AsyncClient()
    set_client(client)
    yield
    await client.aclose()


app = FastAPI(title="orchestrator-api", lifespan=lifespan)

_recent_queries: list[dict] = []


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "mock_agent": USE_MOCK_AGENT}


@app.get("/ready")
async def readiness() -> dict:
    dependencies = {}
    client = get_client()
    for name, url in {"agent": AGENT_SERVICE_URL, "retrieval": RETRIEVAL_URL,
                      "validator": ANSWER_VALIDATOR_URL}.items():
        try:
            result = await client.get(f"{url}/health", timeout=5)
            result.raise_for_status()
            dependencies[name] = result.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            dependencies[name] = False
    return {"ready": all(dependencies.values()) and not USE_MOCK_AGENT,
            "mock_agent": USE_MOCK_AGENT, "dependencies": dependencies}


def _stable_document_id(content: bytes, dataset_id: str | None) -> str:
    if dataset_id:
        normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", dataset_id).strip("._")
        if not normalized:
            raise HTTPException(status_code=400, detail="dataset_id has no usable characters")
        return normalized
    return f"doc_{hashlib.sha256(content).hexdigest()[:16]}"


async def _index_processed_document(client: httpx.AsyncClient, document: dict) -> dict:
    response = await client.post(f"{RETRIEVAL_URL}/ingest", json=document, timeout=120)
    response.raise_for_status()
    ingestion = response.json()
    if ingestion.get("status") != "success" or ingestion.get("total_chunks", 0) < 1:
        raise RuntimeError("retrieval did not confirm at least one indexed chunk")
    return ingestion


@app.post("/documents/ingest")
async def ingest_document(file: UploadFile, dataset_id: str | None = None) -> dict:
    """Route a PDF through processing and retrieval, persisting every state."""
    filename = file.filename or "document.pdf"
    content = await file.read()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    sha256 = hashlib.sha256(content).hexdigest()
    document_id = _stable_document_id(content, dataset_id)
    existing = get_manifest_document(document_id)
    if existing and existing.get("sha256") != sha256:
        raise HTTPException(
            status_code=409,
            detail=f"dataset_id '{document_id}' is already mapped to different content",
        )
    if existing and existing.get("status") == "indexed":
        return existing

    record = update_document(
        document_id,
        dataset_id=dataset_id,
        source_filename=filename,
        sha256=sha256,
        status="uploaded",
        uploaded_at=existing.get("uploaded_at") if existing else datetime.now(timezone.utc).isoformat(),
        error=None,
        failed_at=None,
        failed_stage=None,
    )

    try:
        client = get_client()
        processed_response = await client.post(
            f"{DOC_PROCESSOR_URL}/process",
            params={"document_id": document_id},
            files={"file": (filename, content, "application/pdf")},
            timeout=900,
        )
        processed_response.raise_for_status()
        processed = processed_response.json()
        record = update_document(
            document_id,
            status="processed",
            processed_at=datetime.now(timezone.utc).isoformat(),
            page_count=processed.get("page_count"),
        )
        ingestion = await _index_processed_document(client, processed)
        record = update_document(
            document_id,
            status="indexed",
            indexed_at=datetime.now(timezone.utc).isoformat(),
            total_chunks=ingestion.get("total_chunks", 0),
        )
        return record
    except Exception as exc:
        stage = "retrieval" if record.get("status") == "processed" else "processor"
        update_document(
            document_id,
            status="failed",
            failed_stage=stage,
            failed_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail=f"{stage} dependency failed") from exc


@app.post("/documents/{document_id}/resume")
async def resume_ingestion(document_id: str) -> dict:
    """Resume indexing from persisted processor output without reprocessing."""
    record = get_manifest_document(document_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No ingestion record '{document_id}'")
    if record.get("status") == "indexed":
        return record
    if not record.get("processed_at"):
        raise HTTPException(status_code=409, detail="Document must be uploaded again; processing did not complete")

    try:
        client = get_client()
        processed_response = await client.get(
            f"{DOC_PROCESSOR_URL}/documents/{document_id}", timeout=30
        )
        processed_response.raise_for_status()
        ingestion = await _index_processed_document(client, processed_response.json())
        return update_document(
            document_id,
            status="indexed",
            indexed_at=datetime.now(timezone.utc).isoformat(),
            total_chunks=ingestion.get("total_chunks", 0),
            error=None,
            failed_at=None,
            failed_stage=None,
        )
    except Exception as exc:
        update_document(
            document_id,
            status="failed",
            failed_stage="retrieval",
            failed_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
        )
        raise HTTPException(status_code=502, detail="retrieval dependency failed") from exc


@app.get("/ingestion")
def ingestion_status() -> dict:
    records = list_manifest_documents()
    counts = {
        "uploaded": sum(bool(record.get("uploaded_at")) for record in records),
        "processed": sum(bool(record.get("processed_at")) for record in records),
        "indexed": sum(record.get("status") == "indexed" for record in records),
        "failed": sum(record.get("status") == "failed" for record in records),
    }
    return {"counts": counts, "documents": records}


@app.get("/documents")
async def list_documents() -> list[dict]:
    indexed = list_manifest_documents(status="indexed")
    client = get_client()
    documents = []
    for record in indexed:
        doc_id = record["document_id"]
        try:
            detail_resp = await client.get(f"{DOC_PROCESSOR_URL}/documents/{doc_id}", timeout=30)
            detail_resp.raise_for_status()
        except httpx.HTTPError as e:
            print(f"[orchestrator] Skipping document '{doc_id}': {e}")
            continue
        documents.append(_to_ui_summary(detail_resp.json(), record))

    return documents


@app.get("/documents/{document_id}")
async def get_document(document_id: str) -> dict:
    record = get_manifest_document(document_id)
    if not record or record.get("status") != "indexed":
        raise HTTPException(status_code=404, detail=f"No indexed document '{document_id}'")
    resp = await get_client().get(f"{DOC_PROCESSOR_URL}/documents/{document_id}", timeout=30)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"No document '{document_id}'")
    resp.raise_for_status()
    return _to_ui_summary(resp.json(), record)


@app.get("/documents/{document_id}/pdf")
async def get_document_pdf(
    document_id: str,
    range_header: str | None = Header(None, alias="Range"),
):
    """Stream a stored source PDF without exposing the processor service."""
    headers = {"Range": range_header} if range_header else None
    client = get_client()
    upstream = await client.send(
        client.build_request(
            "GET", f"{DOC_PROCESSOR_URL}/documents/{document_id}/pdf", headers=headers
        ),
        stream=True,
    )
    if upstream.status_code == 404:
        await upstream.aclose()
        raise HTTPException(status_code=404, detail="Source PDF is unavailable")
    if upstream.status_code >= 400:
        await upstream.aclose()
        raise HTTPException(status_code=502, detail="PDF storage dependency failed")

    forwarded = {
        key: value for key, value in upstream.headers.items()
        if key.lower() in {
            "accept-ranges", "content-disposition", "content-length", "content-range",
            "etag", "last-modified",
        }
    }
    return StreamingResponse(
        upstream.aiter_bytes(),
        status_code=upstream.status_code,
        media_type="application/pdf",
        headers=forwarded,
        background=BackgroundTask(upstream.aclose),
    )


def _to_ui_summary(processed_document: dict, record: dict | None = None) -> dict:
    """Reshape a full ProcessedDocument (doc-processor-api's format) into
    the smaller summary shape ui-service's client.py expects."""
    tables_detected = sum(len(page["tables"]) for page in processed_document["pages"])
    return {
        "document_id": processed_document["document_id"],
        "name": processed_document["source_filename"],
        "pages": processed_document["page_count"],
        "tables_detected": tables_detected,
        "structured_values": {},  # nothing extracts this yet, either doc-processor-api needs to extract it, or it's actually eval-service's/agent-service's job later.
        "status": (record or {}).get("status", "processed"),
    }


def _insufficient_evidence(reason: str) -> dict:
    return {"answer_type": "insufficient_evidence", "evidence": [], "params": {"reason": reason}}


class AskRequest(BaseModel):
    question: str
    document_id: str | None = None
    include_diagnostics: bool = False
    evaluation_variant: str = "reranker_on"
    request_id: str | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None


class AskDiagnosticResponse(BaseModel):
    answer: Answer
    diagnostics: dict


@app.post(
    "/ask",
    response_model=Answer | AskDiagnosticResponse,
    response_model_exclude_none=True,
)
async def ask(request: AskRequest, response: Response) -> dict:
    start = time.perf_counter()
    if request.evaluation_variant not in {"reranker_on", "reranker_off"}:
        raise HTTPException(status_code=422, detail="unknown evaluation_variant")
    request_id = request.request_id or uuid.uuid4().hex
    trace_id = request.trace_id or hashlib.sha256(request_id.encode("utf-8")).hexdigest()[:32]
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Langfuse-Trace-ID"] = trace_id
    agent_diagnostics = {}
    validation = {"valid": False, "reason": "validation was not completed"}

    try:
        with observation(
            "orchestrator.ask",
            trace_id=trace_id,
            parent_span_id=request.parent_span_id,
            input={"question": request.question, "document_id": request.document_id},
            metadata={"request_id": request_id, "variant": request.evaluation_variant},
        ) as orchestrator_span:
            agent_result = await ask_agent(
                request.question,
                request.document_id,
                include_diagnostics=request.include_diagnostics,
                evaluation_variant=request.evaluation_variant,
                request_id=request_id,
                trace_id=trace_id,
                parent_span_id=orchestrator_span.observation_id,
            )
            if request.include_diagnostics:
                candidate_answer = agent_result.get("answer")
                agent_diagnostics = agent_result.get("diagnostics") or {}
            else:
                candidate_answer = agent_result
                agent_diagnostics = {}
            if not isinstance(candidate_answer, dict):
                raise ValueError("agent-service returned an invalid answer")
            validation = await validate(
                candidate_answer,
                trace_id=trace_id,
                parent_span_id=orchestrator_span.observation_id,
            )

            if validation["valid"]:
                final_answer = validation["answer"]
            else:
                # Never forward a rejected answer. Validate the controlled
                # fallback as well so every public answer uses the same contract.
                final_answer = {
                    "answer_type": "insufficient_evidence",
                    "evidence": [],
                    "params": {
                        "reason": f"Answer failed validation: {validation['reason']}"
                    },
                }
                fallback_validation = await validate(
                    final_answer,
                    trace_id=trace_id,
                    parent_span_id=orchestrator_span.observation_id,
                )
                if not fallback_validation.get("valid"):
                    raise HTTPException(
                        status_code=500,
                        detail="validator rejected fallback answer",
                    )
                final_answer = fallback_validation["answer"]
            orchestrator_span.update(
                output={
                    "answer_type": final_answer.get("answer_type"),
                    "validation_valid": validation.get("valid"),
                }
            )
    except (AgentDependencyError, httpx.HTTPError, ValueError, KeyError) as exc:
        reason = f"Downstream service error: {type(exc).__name__}"
        final_answer = _insufficient_evidence(reason)
        validation = {"valid": False, "reason": reason}

    latency_ms = round((time.perf_counter() - start) * 1000)
    _recent_queries.append({
        "question": request.question,
        "latency_ms": latency_ms,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    })

    if request.include_diagnostics:
        return {
            "answer": final_answer,
            "diagnostics": {
                "request_id": request_id,
                "trace_id": trace_id,
                "evaluation_variant": request.evaluation_variant,
                "latency_ms": latency_ms,
                "validation": validation,
                "agent": agent_diagnostics,
            },
        }
    return final_answer


@app.get("/dashboard")
async def dashboard() -> dict:
    documents = await list_documents()
    indexed_documents = len(documents)
    try:
        stats_response = await get_client().get(f"{RETRIEVAL_URL}/stats", timeout=30)
        stats_response.raise_for_status()
        indexed_documents = stats_response.json().get("indexed_documents", indexed_documents)
    except (httpx.HTTPError, ValueError):
        pass
    return {
        "num_documents": indexed_documents,
        "documents": documents,
        "recent_queries": _recent_queries[-10:],
    }
