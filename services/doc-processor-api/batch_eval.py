"""
batch_eval.py

Runs process_pdf() across a whole directory of PDFs and reports
STRUCTURAL sanity metrics - not answer accuracy (that's eval-service's
job later, against TAT-DQA's actual Q/A pairs). This is about catching
extraction problems early: PDFs that silently produced almost nothing,
tables that look broken, pages that came back empty.

Usage:
    python batch_eval.py /path/to/pdf/directory [--limit 50]

Writes a report to batch_eval_report.json in the current directory.
"""

import argparse
import json
import time
import traceback
from pathlib import Path

from app.processor import process_pdf


def analyze_document(doc) -> dict:
    """Structural sanity metrics for one ProcessedDocument."""
    total_blocks = sum(len(p.blocks) for p in doc.pages)
    total_tables = sum(len(p.tables) for p in doc.pages)
    total_text_chars = sum(len(b.text) for p in doc.pages for b in p.blocks)

    empty_pages = [
        p.page_number for p in doc.pages
        if not p.blocks and not p.tables
    ]

    # A table with 1 row (just the header, no data) usually means
    # extraction failed to find the table's actual content.
    suspicious_tables = [
        t.table_id for p in doc.pages for t in p.tables
        if t.num_rows <= 1 or t.num_cols <= 1
    ]

    # Rows/cols that don't match the actual row/col list length -
    # would indicate the num_rows/num_cols fix regressed.
    miscounted_tables = [
        t.table_id for p in doc.pages for t in p.tables
        if t.num_rows != len(t.rows) or (t.rows and t.num_cols != len(t.rows[0]))
    ]

    return {
        "document_id": doc.document_id,
        "page_count": doc.page_count,
        "total_blocks": total_blocks,
        "total_tables": total_tables,
        "total_text_chars": total_text_chars,
        "empty_pages": empty_pages,
        "suspicious_tables": suspicious_tables,
        "miscounted_tables": miscounted_tables,
    }


def main(pdf_dir: str, limit: int | None) -> None:
    dir_path = Path(pdf_dir)
    pdf_paths = sorted(dir_path.glob("*.pdf"))
    if limit:
        pdf_paths = pdf_paths[:limit]

    if not pdf_paths:
        print(f"No PDFs found in {pdf_dir}")
        return

    print(f"Processing {len(pdf_paths)} PDFs from {pdf_dir}...\n")

    results = []
    failures = []
    start = time.time()

    for i, path in enumerate(pdf_paths, 1):
        print(f"[{i}/{len(pdf_paths)}] {path.name} ... ", end="", flush=True)
        try:
            doc = process_pdf(str(path))
            analysis = analyze_document(doc)
            results.append(analysis)

            flags = []
            if analysis["total_tables"] == 0:
                flags.append("NO TABLES FOUND")
            if analysis["empty_pages"]:
                flags.append(f"{len(analysis['empty_pages'])} EMPTY PAGE(S)")
            if analysis["suspicious_tables"]:
                flags.append(f"{len(analysis['suspicious_tables'])} SUSPICIOUS TABLE(S)")
            if analysis["miscounted_tables"]:
                flags.append(f"{len(analysis['miscounted_tables'])} MISCOUNTED TABLE(S)")

            print("OK" if not flags else f"FLAGGED: {', '.join(flags)}")

        except Exception as e:
            print(f"FAILED: {e}")
            failures.append({
                "file": path.name,
                "error": str(e),
                "traceback": traceback.format_exc(),
            })

    elapsed = time.time() - start

    # --- aggregate summary ---
    total = len(pdf_paths)
    succeeded = len(results)
    zero_table_docs = [r["document_id"] for r in results if r["total_tables"] == 0]
    docs_with_empty_pages = [r["document_id"] for r in results if r["empty_pages"]]
    docs_with_suspicious_tables = [r["document_id"] for r in results if r["suspicious_tables"]]
    docs_with_miscounted_tables = [r["document_id"] for r in results if r["miscounted_tables"]]

    summary = {
        "total_pdfs": total,
        "succeeded": succeeded,
        "hard_failures": len(failures),
        "avg_seconds_per_pdf": round(elapsed / total, 2) if total else 0,
        "docs_with_zero_tables": zero_table_docs,
        "docs_with_empty_pages": docs_with_empty_pages,
        "docs_with_suspicious_tables": docs_with_suspicious_tables,
        "docs_with_miscounted_tables": docs_with_miscounted_tables,
    }

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total PDFs:              {total}")
    print(f"Succeeded:               {succeeded}")
    print(f"Hard failures (crashed): {len(failures)}")
    print(f"Avg time per PDF:        {summary['avg_seconds_per_pdf']}s")
    print(f"Docs w/ zero tables:     {len(zero_table_docs)}")
    print(f"Docs w/ empty pages:     {len(docs_with_empty_pages)}")
    print(f"Docs w/ suspicious tbls: {len(docs_with_suspicious_tables)}")
    print(f"Docs w/ miscounted tbls: {len(docs_with_miscounted_tables)}  <- should be 0 after the num_rows fix")

    report = {
        "summary": summary,
        "per_document": results,
        "failures": failures,
    }
    with open("batch_eval_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nFull report written to batch_eval_report.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf_dir", help="Directory containing PDFs to process")
    parser.add_argument("--limit", type=int, default=None, help="Max number of PDFs to process")
    args = parser.parse_args()
    main(args.pdf_dir, args.limit)