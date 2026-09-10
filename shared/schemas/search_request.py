from typing import Literal, Optional

from pydantic import BaseModel, Field

class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    document_id: Optional[str] = None  # Optional: restrict search to a specific PDF
    limit: int = Field(default=5, ge=1, le=100)
    content_type: Optional[Literal["text", "table"]] = None
    section: Optional[str] = None
    rerank: bool = True
    include_diagnostics: bool = False
