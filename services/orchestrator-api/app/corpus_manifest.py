"""Durable, atomic state for the PDF -> processed -> indexed pipeline."""

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import CORPUS_MANIFEST_PATH

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty() -> dict:
    return {"version": 1, "documents": {}}


def read_manifest() -> dict:
    with _lock:
        if not CORPUS_MANIFEST_PATH.exists():
            return _empty()
        try:
            return json.loads(CORPUS_MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"Cannot read corpus manifest: {exc}") from exc


def _write(manifest: dict) -> None:
    CORPUS_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        dir=CORPUS_MANIFEST_PATH.parent,
        prefix="corpus-manifest-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary:
            json.dump(manifest, temporary, indent=2, sort_keys=True)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, CORPUS_MANIFEST_PATH)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def update_document(document_id: str, **changes) -> dict:
    with _lock:
        if CORPUS_MANIFEST_PATH.exists():
            try:
                manifest = json.loads(CORPUS_MANIFEST_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise RuntimeError(f"Cannot read corpus manifest: {exc}") from exc
        else:
            manifest = _empty()
        record = manifest["documents"].setdefault(
            document_id, {"document_id": document_id, "created_at": _now()}
        )
        record.update(changes)
        record["updated_at"] = _now()
        _write(manifest)
        return record.copy()


def get_document(document_id: str) -> dict | None:
    return read_manifest()["documents"].get(document_id)


def list_documents(status: str | None = None) -> list[dict]:
    records = list(read_manifest()["documents"].values())
    if status:
        records = [record for record in records if record.get("status") == status]
    return sorted(records, key=lambda record: record["document_id"])
