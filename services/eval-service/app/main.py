"""FastAPI entrypoint for reproducible LEDGER evaluation."""

from __future__ import annotations

from pathlib import Path
import httpx

from fastapi import FastAPI, HTTPException, Query, status

from app.config import (
    ROOT_DIR,
    DEFAULT_DATASET_PATH,
    EVAL_DATA_DIR,
    LANGFUSE_REQUIRED,
    ORCHESTRATOR_URL,
)
from app.dataset import build_manifest, write_manifest, read_manifest
from app.langfuse_client import LangfuseBridge
from app.metrics import aggregate_results
from app.models import DatasetImportRequest, RunRequest
from app.runner import EvaluationRunner
from app.storage import RunStorage


app = FastAPI(
    title="eval-service",
    version="1.0.0",
    description="Held-out TAT-DQA evaluation, metrics, artifacts, and Langfuse linkage.",
)
storage = RunStorage(EVAL_DATA_DIR)
langfuse = LangfuseBridge()
runner = EvaluationRunner(storage, langfuse)


@app.get("/health")
def health() -> dict:
    telemetry = langfuse.health()
    ready = not LANGFUSE_REQUIRED or telemetry["ready"]
    return {
        "status": "ok" if ready else "degraded",
        "service": "eval-service",
        "storage": str(EVAL_DATA_DIR),
        "default_dataset_exists": DEFAULT_DATASET_PATH.exists(),
        "langfuse": telemetry,
    }


@app.post("/datasets/import")
def import_dataset(request: DatasetImportRequest) -> dict:
    source = Path(request.source_path).resolve() if request.source_path else DEFAULT_DATASET_PATH
    if not source.exists():
        raise HTTPException(status_code=404, detail=f"dataset not found: {source}")
    try:
        manifest = build_manifest(
            source,
            name=request.name,
            seed=request.seed,
            selection_fraction=request.selection_fraction,
            max_items=request.max_items,
            split=request.split,
        )
        path = write_manifest(manifest, storage.manifest_path(manifest.manifest_id))
        remote = (
            langfuse.import_dataset(manifest)
            if request.upload_to_langfuse
            else {"uploaded": False, "reason": "upload disabled"}
        )
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "manifest_id": manifest.manifest_id,
        "manifest_path": str(path),
        "items": len(manifest.items),
        "source_sha256": manifest.source_sha256,
        "langfuse": remote,
    }


@app.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_run(request: RunRequest) -> dict:
    if (request.require_langfuse or LANGFUSE_REQUIRED) and not langfuse.ready:
        raise HTTPException(status_code=503, detail="Langfuse is required but not ready")
    if any(k < 1 for k in request.k_values):
        raise HTTPException(status_code=422, detail="all K values must be positive")
    try:
        effective_request = request
        if request.manifest_path:
            supplied = Path(request.manifest_path)
            manifest_path = (supplied if supplied.is_absolute() else ROOT_DIR / supplied).resolve()
            effective_request = RunRequest.model_validate(
                {**request.model_dump(mode="python"), "manifest_path": str(manifest_path)}
            )
        else:
            manifest = build_manifest(DEFAULT_DATASET_PATH, name="tat-dqa-held-out")
            manifest_path = write_manifest(
                manifest, storage.manifest_path(manifest.manifest_id)
            )
            effective_request = RunRequest.model_validate(
                {**request.model_dump(mode="python"), "manifest_path": str(manifest_path)}
            )
        if effective_request.orchestrator_url is None:
            effective_request = RunRequest.model_validate(
                {
                    **effective_request.model_dump(mode="python"),
                    "orchestrator_url": ORCHESTRATOR_URL,
                }
            )
        async with httpx.AsyncClient(timeout=10) as client:
            base = str(effective_request.orchestrator_url).rstrip("/")
            ready = await client.get(f"{base}/ready")
            ready.raise_for_status()
            if not ready.json().get("ready"):
                raise HTTPException(status_code=503, detail={"message": "QA dependencies are not ready", **ready.json()})
            ingestion = await client.get(f"{base}/ingestion")
            ingestion.raise_for_status()
        indexed = {row["document_id"] for row in ingestion.json().get("documents", [])
                   if row.get("status") == "indexed"}
        selected = read_manifest(manifest_path).items
        if effective_request.max_items:
            selected = selected[:effective_request.max_items]
        missing = sorted({doc for item in selected for doc in item.document_ids} - indexed)
        if missing:
            raise HTTPException(status_code=409, detail={"message": "Index the required PDFs before evaluation", "missing_document_ids": missing})
        summary = runner.create(effective_request, manifest_path, corpus=ingestion.json())
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Orchestrator readiness check failed; check services and restart with current code") from exc
    except (FileNotFoundError, ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **summary.model_dump(mode="json"),
        "status_url": f"/runs/{summary.run_id}",
    }


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return storage.read_status(run_id).model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.post("/runs/{run_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_run(run_id: str) -> dict:
    try:
        config = storage.read_config(run_id)
        if (LANGFUSE_REQUIRED or config.get("require_langfuse")) and not langfuse.ready:
            raise HTTPException(status_code=503, detail="Langfuse is required but not ready")
        return runner.resume(run_id).model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/runs/{run_id}/metrics")
def get_metrics(run_id: str) -> dict:
    try:
        rows = storage.read_items(run_id)
        if not rows:
            summary = storage.read_status(run_id)
            return {"status": summary.status, "attempted": summary.attempted}
        return aggregate_results(rows)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.get("/runs/{run_id}/items")
def get_items(
    run_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict:
    try:
        storage.read_status(run_id)
        rows = storage.read_items(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
    return {"total": len(rows), "offset": offset, "limit": limit, "items": rows[offset:offset + limit]}


@app.get("/runs/{run_id}/artifacts")
def get_artifacts(run_id: str) -> dict:
    try:
        return storage.artifacts(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc
