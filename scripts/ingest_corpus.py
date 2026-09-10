"""Repeatable corpus ingestion through orchestrator-api.

Usage: python scripts/ingest_corpus.py path/to/pdfs
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Process and index a PDF corpus")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--orchestrator-url", default="http://localhost:8000")
    parser.add_argument("--manifest", type=Path, help="Prioritize documents referenced by this evaluation manifest")
    parser.add_argument("--manifest-items", type=int, help="Use only the first N manifest questions when selecting PDFs")
    parser.add_argument("--only-manifest", action="store_true", help="Index only the selected manifest's PDFs")
    parser.add_argument("--dry-run", action="store_true", help="List selected PDFs without calling any service")
    parser.add_argument("--max-documents", type=int, help="Limit a smoke ingestion; omit for the full corpus")
    args = parser.parse_args()
    if (args.only_manifest or args.manifest_items is not None) and not args.manifest:
        parser.error("--only-manifest and --manifest-items require --manifest")
    if args.manifest_items is not None and args.manifest_items < 1:
        parser.error("--manifest-items must be positive")

    pdfs = ([args.directory] if args.directory.is_file() and args.directory.suffix.lower() == ".pdf"
            else sorted(args.directory.rglob("*.pdf")))
    if not pdfs:
        parser.error(f"no PDFs found under {args.directory}")
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        items = manifest["items"][:args.manifest_items] if args.manifest_items else manifest["items"]
        required = {doc for item in items for doc in item["document_ids"]}
        available = {pdf.stem for pdf in pdfs}
        missing = sorted(required - available)
        if missing:
            parser.error(f"{len(missing)} required PDFs missing: {', '.join(missing)}")
        pdfs.sort(key=lambda pdf: (pdf.stem not in required, str(pdf)))
        if args.only_manifest:
            pdfs = [pdf for pdf in pdfs if pdf.stem in required]
    if args.max_documents is not None:
        if args.max_documents < 1:
            parser.error("--max-documents must be positive")
        pdfs = pdfs[:args.max_documents]

    print(f"Selected {len(pdfs)} PDFs", flush=True)
    if args.dry_run:
        for pdf in pdfs:
            print(pdf)
        return 0

    status_response = httpx.get(f"{args.orchestrator_url}/ingestion", timeout=30)
    status_response.raise_for_status()
    records = {
        (record.get("document_id"), record.get("sha256")): record
        for record in status_response.json().get("documents", [])
        if record.get("sha256")
    }

    failed = 0
    for pdf in pdfs:
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        previous = records.get((pdf.stem, digest))
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
                        timeout=1200,
                    )
            response.raise_for_status()
            print(f"INDEXED {pdf} -> {response.json()['document_id']}")
        except httpx.HTTPError as exc:
            failed += 1
            detail = f"; {exc.response.text}" if isinstance(exc, httpx.HTTPStatusError) else ""
            print(f"FAILED  {pdf}: {exc}{detail}", file=sys.stderr, flush=True)

    print(f"Completed: {len(pdfs) - failed} succeeded, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
