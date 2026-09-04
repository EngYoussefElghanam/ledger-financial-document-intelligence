from pydantic import BaseModel
from typing import Optional

class SearchRequest(BaseModel):
    query: str                   # The user's question, e.g., "What is the Q3 revenue?"
    document_id: Optional[str] = None  # Optional: restrict search to a specific PDF
    limit: int = 5               # How many chunks to return to the agent