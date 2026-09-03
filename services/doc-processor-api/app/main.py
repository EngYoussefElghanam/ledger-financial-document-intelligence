"""
The FastAPI surface for doc-processor-api. Deliberately thin - all the
real work (docling wrapping, schema mapping) lives in processor.py.
This file's only job is: accept HTTP requests, call process_pdf(),
persist results, and hand back JSON. No docling-specific logic here.
"""

import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile

from app.processor import process_pdf
from schemas import ProcessedDocument

app = FastAPI(title="doc-processor-api")

# Where processed output gets persisted, so retrieval-api (or anyone else)
# can read it later without re-processing or hitting this API again.
# In Docker this should be a mounted volume shared with retrieval-api.
PROCESSED_DIR = Path("data/processed")
UPLOADS_DIR = Path("data/uploads")
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/health")
def health() -> dict:
    """Basic liveness check - lets the orchestrator (or Docker healthcheck)
    confirm this service is up before routing requests to it."""
    return {"status": "ok"}


@app.post("/process", response_model=ProcessedDocument)
def process_document(file: UploadFile, document_id: str | None = None) -> ProcessedDocument:
    """
    Accepts one PDF upload, runs it through process_pdf(), persists the
    structured result to disk, and returns it.

    document_id is optional - if the caller doesn't specify one,
    process_pdf() defaults it to the filename stem. Passing it explicitly
    lets the orchestrator control ids consistently across a batch ingest
    (e.g. matching TAT-DQA's own doc_XXX naming).
    """
    if file.content_type != "application/pdf" and not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Save the upload to disk first - docling's converter takes a path,
    # not an in-memory stream, so this is a real step, not boilerplate.
    upload_path = UPLOADS_DIR / file.filename
    with upload_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        result = process_pdf(str(upload_path), document_id=document_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    _persist(result)
    return result


@app.post("/process_batch")
def process_batch(directory: str) -> dict:
    """
    Points at a directory of PDFs already sitting on disk (e.g. the
    unpacked TAT-DQA corpus) and processes every one. This is the endpoint
    for indexing the whole corpus in one go, rather than uploading
    thousands of files individually through /process.

    Returns a summary rather than every ProcessedDocument inline -
    with a few thousand documents that response body would be huge and
    not actually useful; callers should read persisted files instead.
    """
    dir_path = Path(directory)
    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"{directory} is not a valid directory")

    pdf_paths = sorted(dir_path.glob("*.pdf"))
    if not pdf_paths:
        raise HTTPException(status_code=400, detail=f"No PDFs found in {directory}")

    succeeded: list[str] = []
    failed: list[dict] = []

    for pdf_path in pdf_paths:
        try:
            result = process_pdf(str(pdf_path))
            _persist(result)
            succeeded.append(result.document_id)
        except Exception as e:
            # One bad PDF shouldn't kill the whole batch - record it and
            # keep going, so a single malformed file doesn't block
            # indexing the other few thousand.
            failed.append({"file": pdf_path.name, "error": str(e)})

    return {
        "total": len(pdf_paths),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "succeeded_ids": succeeded,
        "failures": failed,
    }


@app.get("/documents/{document_id}", response_model=ProcessedDocument)
def get_document(document_id: str) -> ProcessedDocument:
    """
    Returns a previously processed document by id, read from disk rather
    than reprocessed. This is what retrieval-api (or the UI) should call
    to fetch a specific document's structured content without paying the
    docling processing cost again.
    """
    path = PROCESSED_DIR / f"{document_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"No processed document '{document_id}'")
    return ProcessedDocument.model_validate_json(path.read_text())


@app.get("/documents")
def list_documents() -> dict:
    """Lists all currently-indexed document ids - useful for the UI's
    dashboard view and for sanity-checking a batch run's coverage."""
    ids = [p.stem for p in PROCESSED_DIR.glob("*.json")]
    return {"count": len(ids), "document_ids": sorted(ids)}


def _persist(result: ProcessedDocument) -> None:
    """Writes a ProcessedDocument to data/processed/{document_id}.json.
    Centralized here so /process and /process_batch persist identically -
    one place to change the storage format or location later."""
    path = PROCESSED_DIR / f"{result.document_id}.json"
    path.write_text(result.model_dump_json(indent=2))