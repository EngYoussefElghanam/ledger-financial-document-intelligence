import uuid
from fastapi import FastAPI, HTTPException
from shared.schemas.document import ProcessedDocument
from shared.schemas.search_request import SearchRequest
from qdrant_client import models

from app.chunker import create_chunks
from app.database import qdrant_client, init_db
from app.embeddings import get_dense_vector, get_sparse_vector

app = FastAPI(title="Retrieval API", description="An API that retrievs the relevant parts from the document")

# Setup database on startup
init_db()

@app.post("/ingest")
async def ingest_document(doc: ProcessedDocument):
    try:

        # Creates the chunks from the doc
        chunks = create_chunks(doc)

        # Qdrant (our vector database) requires that we store each item as a "point" object
        points_to_upsert = []
        
        for chunk in chunks:

            # We convert the chunk to 2 vector represntations, each with its own benefits
            # And then we use them together to better our search
            dense_vec = get_dense_vector(chunk.text) # This is good in understand the context of the search
            sparse_vec = get_sparse_vector(chunk.text) # This is good in matching keywords from the search query
            
            # Package vectors and payload together
            points_to_upsert.append(
                models.PointStruct(
                    id=str(uuid.uuid4()), # A unique id for our point
                    vector={
                        "dense": dense_vec,
                        "bm25": models.SparseVector(
                            indices=sparse_vec["indices"], 
                            values=sparse_vec["values"]
                        )
                    },
                    # We only use the vectors for search; but the ai model will need the original text;
                    # So we must attach it with the point object
                    payload={"text": chunk.text, **chunk.metadata} # Stores metadata(id, type,...) for the chunk and the original text
                )
            )

        # Save to our database
        qdrant_client.upsert(
            collection_name="financials", 
            points=points_to_upsert
        )
        
        return {"status": "success", "total_chunks": len(chunks)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
async def search_documents(request: SearchRequest):
    try:

        # Translate query to vectors
        dense_vec = get_dense_vector(request.query)
        sparse_vec = get_sparse_vector(request.query)

        # A filter is used if the agent wants to search one specific document
        query_filter = None
        if request.document_id:
            query_filter = models.Filter(
                must = [
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchValue(value=request.document_id)
                    )
                ]
            )

        # Perform search
        search_results = qdrant_client.query_points(
            collection_name="financials",
            prefetch=[
                # Search by meaning
                models.Prefetch(
                    query=dense_vec,
                    using="dense",
                    limit=request.limit,
                ),
                # Search by exact keyword match
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vec["indices"],
                        values=sparse_vec["values"]
                    ),
                    using="bm25",
                    limit=request.limit,
                )
            ],
            # Fuse the two sub-queries together
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=query_filter,
            limit=request.limit
        )

        formatted_results = []
        for point in search_results.points:
            formatted_results.append({
                "score": point.score,
                "text": point.payload.get("text"),
                "metadata": {
                    "document_id": point.payload.get("document_id"),
                    "page_number": point.payload.get("page_number"),
                    "section": point.payload.get("section"),
                    "type": point.payload.get("type")
                }
            })

        return {"results": formatted_results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))