from pydantic import BaseModel
from typing import Optional

class SearchFilterRequest(BaseModel):
    """
    Schema for exact metadata lookups without semantic vector search.
    
    Attributes:
        document_id: The exact ID of the document to retrieve chunks from (Required).
        type: The specific content type to filter by
        section: The exact section header to filter by
        limit: The maximum number of chunks to return. Defaults to 50.
    """
    document_id: str
    type: Optional[str] = None  # e.g., "table" or "text"
    section: Optional[str] = None
    limit: int = 50