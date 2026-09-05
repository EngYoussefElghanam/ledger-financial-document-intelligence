from pydantic import BaseModel, Field
from typing import Literal

ContentType = Literal["heading", "paragraph", "table", "list_item", "caption"]


class Block(BaseModel):
    block_id: str
    content_type: ContentType
    text: str
    section: str
    bbox: list[float] = Field(..., min_length=4, max_length=4)  # [x0, y0, x1, y1]


class Table(BaseModel):
    table_id: str
    content_type: Literal["table"] = "table"
    section: str
    caption: str | None = None
    bbox: list[float] = Field(..., min_length=4, max_length=4)
    num_rows: int
    num_cols: int
    rows: list[list[str]]


class Page(BaseModel):
    page_number: int
    blocks: list[Block]
    tables: list[Table]


class ProcessedDocument(BaseModel):
    document_id: str
    source_filename: str
    page_count: int
    pages: list[Page]