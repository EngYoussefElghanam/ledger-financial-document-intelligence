"""Bulk-submit processed document JSON files to retrieval-api."""

import json
import os
from pathlib import Path

import httpx


RETRIEVAL_API_URL = os.getenv("RETRIEVAL_API_URL", "http://localhost:8002").rstrip("/")
PROCESSED_DIR = Path(os.getenv("PROCESSED_DIR", "data/processed")).resolve()


def index_all_files() -> int:
    """Submit every processed JSON document and return the failure count."""
    if not PROCESSED_DIR.is_dir():
        raise SystemExit(f"Processed-document directory does not exist: {PROCESSED_DIR}")

    failures = 0
    with httpx.Client(timeout=120.0) as client:
        for file_path in sorted(PROCESSED_DIR.glob("*.json")):
            print(f"Indexing {file_path.name}...")
            try:
                document = json.loads(file_path.read_text(encoding="utf-8"))
                response = client.post(f"{RETRIEVAL_API_URL}/ingest", json=document)
                response.raise_for_status()
                print(f"Indexed {file_path.name}: {response.json()}")
            except (OSError, json.JSONDecodeError, httpx.HTTPError) as exc:
                failures += 1
                print(f"Failed {file_path.name}: {exc}")
    return failures


if __name__ == "__main__":
    raise SystemExit(1 if index_all_files() else 0)
