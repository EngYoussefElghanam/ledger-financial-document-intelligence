from shared.schemas.document import ProcessedDocument
from chunk_schema import Chunk



def create_chunks(doc: ProcessedDocument):
    """
        Transforms a document into a list of context-rich chunks, using these 2 methods:
        1. Parent-Child Chunking: Associates a section with its title and groups them in a chunk.
        2. Table Chunking: Flattens a 2D table into a readable string

        Input: ProcessedDocument
        
        Output: A list of Chunks
    """
    chunks = []

    for page in doc.pages:
        current_heading = "General Context"

        # Parent-Child text chunking
        # This is used to group each section with its title into 1 chunk
        for block in page.blocks:
            if block.content_type == "heading":
                current_heading = block.text

            elif block.content_type in ["paragraph", "list_item"]:
                rich_text = f"Section: {current_heading} \n Content: {block.text}"

                chunks.append(
                    Chunk(
                        chunk_id=block.block_id,
                        text=rich_text,
                        metadata={
                            "document_id": doc.document_id,
                            "page_number": page.page_number,
                            "type": "text",
                            "section": block.section
                        }
                    )
                )

        for table in page.tables:
            caption_text = table.caption if table.caption else "Untitled Table"
            
            rows_str = "\n".join([" | ".join(row) for row in table.rows])
            table_rich_text = f"Section: {table.section}\nTable Caption: {caption_text}\nData:\n{rows_str}"
            
            chunks.append(Chunk(
                chunk_id=table.table_id,
                text=table_rich_text,
                metadata={
                    "document_id": doc.document_id,
                    "page_number": page.page_number,
                    "type": "table",
                    "section": table.section
                }
            ))

    return chunks