from pydantic import BaseModel

class Chunk(BaseModel):
    chunk_id: str
    text: str  
    metadata: dict