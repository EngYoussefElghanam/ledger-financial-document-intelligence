"""
Run this against ONE sample PDF before touching processor.py.

Purpose: docling's exact output shape (attribute names, how bbox is stored,
what a table's dataframe looks like) is easy to get subtly wrong from memory
or docs alone. This script just prints the raw objects so you can confirm
the mapping logic in processor.py against what docling *actually* gives you
on your real TAT-DQA PDFs, rather than what the docs describe in the abstract.

Usage:
    python explore_docling.py path/to/sample.pdf
"""

import sys

from docling.document_converter import DocumentConverter
from docling_core.types.doc import SectionHeaderItem, TableItem, TextItem


def main(pdf_path: str) -> None:
    converter = DocumentConverter()
    result = converter.convert(pdf_path)
    doc = result.document

    print(f"\n=== Document: {pdf_path} ===")
    print(f"Pages: {doc.num_pages()}")

    print("\n--- First 10 items in reading order (iterate_items) ---")
    for i, (item, level) in enumerate(doc.iterate_items()):
        if i >= 10:
            break
        item_type = type(item).__name__
        page_no = item.prov[0].page_no if getattr(item, "prov", None) else None
        bbox = item.prov[0].bbox if getattr(item, "prov", None) else None
        text_preview = getattr(item, "text", "")[:60]
        print(f"[{i}] type={item_type} level={level} page={page_no} "
              f"bbox={bbox} text={text_preview!r}")

    print("\n--- Section headers found ---")
    for item, _ in doc.iterate_items():
        if isinstance(item, SectionHeaderItem):
            print(f"  level={item.level} text={item.text!r}")

    print("\n--- Tables found ---")
    for i, table in enumerate(doc.tables):
        page_no = table.prov[0].page_no if table.prov else None
        print(f"\nTable {i} (page {page_no}):")
        try:
            df = table.export_to_dataframe(doc=doc)
            print(df.head())
            print(f"shape={df.shape}")
        except Exception as e:
            print(f"  could not export to dataframe: {e}")

    print("\n--- Raw dict of first table (to inspect caption/bbox fields) ---")
    if doc.tables:
        import json
        print(json.dumps(doc.tables[0].model_dump(mode="json"), indent=2)[:2000])


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python explore_docling.py path/to/sample.pdf")
        sys.exit(1)
    main(sys.argv[1])