import uuid
from fastapi import FastAPI, HTTPException
from schemas.document import ProcessedDocument
from schemas.search_request import SearchRequest
from qdrant_client import models

from app.chunker import create_chunks
from app.database import qdrant_client, init_db
from app.embeddings import get_dense_vector, get_sparse_vector, get_rerank_scores

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
                    # uuid5 makes a unique determinestic id based on some input you give it (chunk_id in this case)
                    # we use uuid5 instead of 4, as this helps us generate the same id if the user enters-
                    # duplicate files in the program
                    id=str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk.chunk_id)), # A unique id for our point
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

        fetch_limit = max(request.limit * 4, 20) # set minimum fetched chunks to 20

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
        # This performs 2 searchs, one use the "dense" and one using "bm25"
        # Each search returns results of size fetch_limit, thus the total search has size 2 * fetch_limit
        # Then the 2 search results are ranked using models.fusion.RRF, and then trimmed to the top-
        # fetch_limit results
        # We limit it at fetch_limit and not request_limit as we fetch a relatively big subset here-
        # which will be passed to another ranking algorithm, then the results are trimmed to the first-
        # "request_limit" chunks
        search_results = qdrant_client.query_points(
            collection_name="financials",
            prefetch=[
                # Search by meaning
                models.Prefetch(
                    query=dense_vec,
                    using="dense",
                    limit=fetch_limit,
                ),
                # Search by exact keyword match
                models.Prefetch(
                    query=models.SparseVector(
                        indices=sparse_vec["indices"],
                        values=sparse_vec["values"]
                    ),
                    using="bm25",
                    limit=fetch_limit,
                )
            ],
            # Fuse the two sub-queries together
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            query_filter=query_filter,
            limit=fetch_limit
        )

        if not search_results.points:
            return {"results": []}

        candidate_texts = [point.payload.get("text") for point in search_results.points]


        # This is an additional ranker that ranks the chunks
        # The idea is that this ranker is heavier and better than the previous method above-
        # so running this on the entire texts is gonna be heavy-
        # so instead we retrieve "fetch_limit" chunks using the lighter ranking method-
        # then we run this heavier one on the fetched subset of chunks-
        # to have better ranks for the chunks
        rerank_scores = get_rerank_scores(request.query, candidate_texts)

        for point, score in zip(search_results.points, rerank_scores):
            point.score = score # Overwrite Qdrant RRF score with the Reranker score

        search_results.points.sort(key=lambda x: x.score, reverse=True)

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

        formatted_results = formatted_results[:request.limit]

        return {"results": formatted_results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))