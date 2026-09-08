"""
processor.py

Wraps docling: takes a raw PDF path in, returns a ProcessedDocument
(the shared schema) out. This is the only file that should know
anything about docling's internal API - main.py should just call
process_pdf() and never touch a DoclingDocument directly. That
keeps docling as an implementation detail we could swap out later
without breaking the FastAPI layer or retrieval-api's contract.
"""

from pathlib import Path
from typing import Optional

from docling.document_converter import DocumentConverter
from docling_core.types.doc import SectionHeaderItem, TableItem, TextItem

from schemas.document import Block, Page, ProcessedDocument, Table

# One converter instance, reused across requests - avoids reloading
# the layout/table models on every single call.
_converter = DocumentConverter()


def _bbox_to_list(bbox) -> list[float]:
    """
    Docling's BoundingBox exposes l/t/r/b (left, top, right, bottom).
    Centralizing this conversion means if docling's bbox representation
    changes, there's exactly one place to fix it.
    """
    if bbox is None:
        return [0.0, 0.0, 0.0, 0.0]
    return [float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)]


def _content_type_for(item) -> str:
    """Maps a docling item to our schema's content_type enum."""
    if isinstance(item, SectionHeaderItem):
        return "heading"
    # docling's ListItem subclasses TextItem; check label if present
    label = getattr(item, "label", None)
    label_name = getattr(label, "value", str(label)).lower() if label else ""
    if "caption" in label_name:
        return "caption"
    if "list" in label_name:
        return "list_item"
    return "paragraph"


def _table_to_schema(table: TableItem, doc, table_index: int, document_id: str,
                      current_section: str) -> Table:
    page_no = table.prov[0].page_no if table.prov else 0
    bbox = _bbox_to_list(table.prov[0].bbox if table.prov else None)

    # Structured rows, not flattened text - keeps the table queryable
    # for retrieval-api's non-vector / direct-lookup requirement.
    df = table.export_to_dataframe(doc=doc)
    header_row = [str(c) for c in df.columns]
    data_rows = df.astype(str).values.tolist()
    rows = [header_row] + data_rows

    caption = None
    caption_fn = getattr(table, "caption_text", None)
    if callable(caption_fn):
        try:
            caption = caption_fn(doc) or None
        except Exception:
            caption = None

    return Table(
        table_id=f"{document_id}_p{page_no}_t{table_index}",
        section=current_section,
        caption=caption,
        bbox=bbox,
        num_rows=len(rows),
        num_cols=len(header_row),
        rows=rows,
    )


def process_pdf(pdf_path: str, document_id: Optional[str] = None) -> ProcessedDocument:
    """
    Converts one PDF into a ProcessedDocument.

    document_id defaults to the filename stem (e.g. "doc_017.pdf" ->
    "doc_017") but can be overridden by the caller, since /process_batch
    will likely want to assign ids consistently across the corpus.
    """
    path = Path(pdf_path)
    doc_id = document_id or path.stem

    result = _converter.convert(str(path))
    doc = result.document

    # page_number -> accumulators, built up as we walk the document once
    # in reading order. Reading order matters here: it's what lets us
    # track "current section" correctly (see current_section below).
    pages_blocks: dict[int, list[Block]] = {}
    pages_tables: dict[int, list[Table]] = {}

    current_section = "Untitled"
    block_counters: dict[int, int] = {}
    table_counters: dict[int, int] = {}
    seen_table_refs = set()

    for item, _level in doc.iterate_items():
        if isinstance(item, TableItem):
            # Tables are also emitted by iterate_items(); handle them once
            # here via doc.tables below to avoid double-processing, but
            # still use their position in the walk to catch the right
            # current_section.
            if item.self_ref in seen_table_refs:
                continue
            seen_table_refs.add(item.self_ref)
            page_no = item.prov[0].page_no if item.prov else 0
            idx = table_counters.get(page_no, 0)
            table_counters[page_no] = idx + 1
            table = _table_to_schema(item, doc, idx, doc_id, current_section)
            pages_tables.setdefault(page_no, []).append(table)
            continue

        if isinstance(item, TextItem):
            if not item.prov:
                continue
            page_no = item.prov[0].page_no
            bbox = _bbox_to_list(item.prov[0].bbox)
            content_type = _content_type_for(item)

            if content_type == "heading":
                current_section = item.text.strip() or current_section

            idx = block_counters.get(page_no, 0)
            block_counters[page_no] = idx + 1
            block = Block(
                block_id=f"{doc_id}_p{page_no}_b{idx}",
                content_type=content_type,
                text=item.text,
                section=current_section,
                bbox=bbox,
            )
            pages_blocks.setdefault(page_no, []).append(block)

    page_numbers = sorted(set(pages_blocks) | set(pages_tables))
    pages = [
        Page(
            page_number=pn,
            blocks=pages_blocks.get(pn, []),
            tables=pages_tables.get(pn, []),
        )
        for pn in page_numbers
    ]

    return ProcessedDocument(
        document_id=doc_id,
        source_filename=path.name,
        page_count=doc.num_pages(),
        pages=pages,
    )