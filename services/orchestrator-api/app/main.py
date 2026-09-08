import httpx
from fastapi import FastAPI, HTTPException

from app.config import DOC_PROCESSOR_URL

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