"""Repeatable corpus ingestion through orchestrator-api.

Usage: python scripts/ingest_corpus.py path/to/pdfs
"""

import argparse
import hashlib
import sys
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Process and index a PDF corpus")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--orchestrator-url", default="http://localhost:8000")
    args = parser.parse_args()

    pdfs = sorted(args.directory.rglob("*.pdf"))
    if not pdfs:
        parser.error(f"no PDFs found under {args.directory}")

    status_response = httpx.get(f"{args.orchestrator_url}/ingestion", timeout=30)
    status_response.raise_for_status()
    records = {
        record.get("sha256"): record
        for record in status_response.json().get("documents", [])
        if record.get("sha256")
    }

    failed = 0
    for pdf in pdfs:
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        previous = records.get(digest)
        try:
            if previous and previous.get("status") == "indexed":
                print(f"SKIP    {pdf} -> {previous['document_id']}")
                continue
            if previous and previous.get("processed_at"):
                response = httpx.post(
                    f"{args.orchestrator_url}/documents/{previous['document_id']}/resume",
                    timeout=180,
                )
            else:
                with pdf.open("rb") as stream:
                    response = httpx.post(
                        f"{args.orchestrator_url}/documents/ingest",
                        params={"dataset_id": pdf.stem},
                        files={"file": (pdf.name, stream, "application/pdf")},
                        timeout=600,
                    )
            response.raise_for_status()
            print(f"INDEXED {pdf} -> {response.json()['document_id']}")
        except httpx.HTTPError as exc:
            failed += 1
            print(f"FAILED  {pdf}: {exc}", file=sys.stderr)

    print(f"Completed: {len(pdfs) - failed} succeeded, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
