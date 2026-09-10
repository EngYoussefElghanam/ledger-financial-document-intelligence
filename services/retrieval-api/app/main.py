import uuid
from fastapi import FastAPI, Header, HTTPException
from schemas.document import ProcessedDocument
from schemas.search_filter_request import SearchFilterRequest
from schemas.search_request import SearchRequest
from qdrant_client import models

from app.chunker import create_chunks
from app.database import qdrant_client, init_db
from app.embeddings import get_dense_vectors, get_sparse_vectors, get_rerank_scores
from ledger_observability import observation

app = FastAPI(title="Retrieval API", description="Retrieve relevant content from financial documents")

# Setup database on startup
init_db()

@app.get("/health")
def health():
    return {"status": "ok", "indexed_chunks": qdrant_client.count(collection_name="financials", exact=True).count}


@app.get("/stats")
def stats():
    document_ids = set()
    offset = None
    while True:
        records, offset = qdrant_client.scroll(
            collection_name="financials",
            offset=offset,
            limit=256,
            with_payload=["document_id"],
            with_vectors=False,
        )
        document_ids.update(
            record.payload.get("document_id")
            for record in records
            if record.payload and record.payload.get("document_id")
        )
        if offset is None:
            break
    return {
        "indexed_chunks": qdrant_client.count(collection_name="financials", exact=True).count,
        "indexed_documents": len(document_ids),
    }

@app.post("/ingest")
def ingest_document(doc: ProcessedDocument):
    try:

        # Creates the chunks from the doc
        chunks = create_chunks(doc)
        if not chunks:
            raise ValueError("Document has no searchable text or tables")

        # A list of the text of all chunks
        chunk_texts = [chunk.text for chunk in chunks]

        # We convert the chunks to 2 vector represntations, each with its own benefits
        # And then we use them together to better our search   
        # We also use fastembed's inner parallelization technique, ie the full text is passed on to fastembed once instead of-
        # passing each chunk on its own, and it processes all the chunks together in parallel
        dense_vectors = get_dense_vectors(chunk_texts) # This is good in understand the context of the search
        sparse_vectors = get_sparse_vectors(chunk_texts) # This is good in matching keywords from the search query

        # Qdrant (our vector database) requires that we store each item as a "point" object
        points_to_upsert = []
        
        for chunk, dense_vec, sparse_vec in zip(chunks, dense_vectors, sparse_vectors):         
            
            # Package vectors and payload together
            points_to_upsert.append(
                models.PointStruct(
                    # uuid5 makes a unique determinestic id based on some input you give it (chunk_id in this case)
                    # we use uuid5 instead of 4, as this helps us generate the same id if the user enters-
                    # duplicate files in the program
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc.document_id}:{chunk.chunk_id}")),
                    vector={
                        "dense": dense_vec,
                        "bm25": models.SparseVector(
                            indices=sparse_vec.indices, 
                            values=sparse_vec.values
                        )
                    },
                    # We only use the vectors for search; but the ai model will need the original text;
                    # So we must attach it with the point object
                    payload={"text": chunk.text, **chunk.metadata} # Stores metadata(id, type,...) for the chunk and the original text
                )
            )

        # Replace this document's points so a shorter reingestion cannot leave
        # stale chunks searchable.
        qdrant_client.delete(
            collection_name="financials",
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=doc.document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )

        # Save to our database
        qdrant_client.upsert(
            collection_name="financials", 
            points=points_to_upsert,
            wait=True,
        )
        
        return {"status": "success", "total_chunks": len(chunks)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _search_documents(request: SearchRequest):
    try:

        # Translate query to vectors
        # We pass the query as a list, as our functions expects a list of strings
        # Also the function returns a list of vectors, and since we only expect there to be one vector-
        # which is the vector embedding for the query we sent, then we only take the 0th vector in the list-
        # Which is the only vector there
        with observation(
            "retrieval.embed_query",
            as_type="embedding",
            input={"query": request.query},
        ) as embedding_span:
            dense_vec = get_dense_vectors([request.query])[0]
            sparse_vec = get_sparse_vectors([request.query])[0]
            embedding_span.update(output={"dense_dimensions": len(dense_vec)})

        fetch_limit = max(request.limit * 4, 20) # set minimum fetched chunks to 20

        # Apply metadata filters before candidate selection.
        conditions = []
        if request.document_id:
            conditions.append(
                models.FieldCondition(
                    key="document_id", match=models.MatchValue(value=request.document_id)
                )
            )
        if request.content_type:
            conditions.append(
                models.FieldCondition(
                    key="type", match=models.MatchValue(value=request.content_type)
                )
            )
        if request.section:
            conditions.append(
                models.FieldCondition(
                    key="section", match=models.MatchValue(value=request.section)
                )
            )
        query_filter = models.Filter(must=conditions) if conditions else None

        # Perform search
        # This performs 2 searchs, one use the "dense" and one using "bm25"
        # Each search returns results of size fetch_limit, thus the total search has size 2 * fetch_limit
        # Then the 2 search results are ranked using models.fusion.RRF, and then trimmed to the top-
        # fetch_limit results
        # We limit it at fetch_limit and not request_limit as we fetch a relatively big subset here-
        # which will be passed to another ranking algorithm, then the results are trimmed to the first-
        # "request_limit" chunks
        with observation(
            "retrieval.hybrid_rrf",
            input={"fetch_limit": fetch_limit, "filters": bool(query_filter)},
        ) as hybrid_span:
            search_results = qdrant_client.query_points(
                collection_name="financials",
                prefetch=[
                    models.Prefetch(query=dense_vec, using="dense", limit=fetch_limit),
                    models.Prefetch(
                        query=models.SparseVector(
                            indices=sparse_vec.indices, values=sparse_vec.values
                        ),
                        using="bm25",
                        limit=fetch_limit,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                query_filter=query_filter,
                limit=fetch_limit,
            )
            hybrid_span.update(output={"candidate_count": len(search_results.points)})

        if not search_results.points:
            response = {"results": []}
            if request.include_diagnostics:
                response["diagnostics"] = {
                    "reranker_enabled": request.rerank,
                    "candidate_count": 0,
                    "candidates": [],
                }
            return response

        candidate_texts = [point.payload.get("text") for point in search_results.points]
        candidate_diagnostics = [
            {
                "chunk_id": point.payload.get("chunk_id"),
                "rank": rank,
                "score": point.score,
                "document_id": point.payload.get("document_id"),
                "page_number": point.payload.get("page_number"),
            }
            for rank, point in enumerate(search_results.points, start=1)
        ]


        # This is an additional ranker that ranks the chunks
        # The idea is that this ranker is heavier and better than the previous method above-
        # so running this on the entire texts is gonna be heavy-
        # so instead we retrieve "fetch_limit" chunks using the lighter ranking method-
        # then we run this heavier one on the fetched subset of chunks-
        # to have better ranks for the chunks
        if request.rerank:
            with observation(
                "retrieval.cross_encoder_rerank",
                input={"query": request.query, "candidate_count": len(candidate_texts)},
            ) as rerank_span:
                rerank_scores = get_rerank_scores(request.query, candidate_texts)
                rerank_span.update(output={"score_count": len(rerank_scores)})

            for point, score in zip(search_results.points, rerank_scores):
                point.score = score

            search_results.points.sort(key=lambda x: x.score, reverse=True)

        formatted_results = []
        for rank, point in enumerate(search_results.points, start=1):
            formatted_results.append({
                "chunk_id": point.payload.get("chunk_id"),
                "rank": rank,
                "score": point.score,
                "text": point.payload.get("text"),
                "metadata": {
                    "document_id": point.payload.get("document_id"),
                    "source_filename": point.payload.get("source_filename"),
                    "page_number": point.payload.get("page_number"),
                    "section": point.payload.get("section"),
                    "type": point.payload.get("type")
                }
            })

        formatted_results = formatted_results[:request.limit]

        response = {"results": formatted_results}
        if request.include_diagnostics:
            response["diagnostics"] = {
                "reranker_enabled": request.rerank,
                "candidate_count": len(candidate_diagnostics),
                "candidates": candidate_diagnostics,
            }
        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search")
def search_documents(
    request: SearchRequest,
    x_langfuse_trace_id: str | None = Header(default=None),
    x_langfuse_parent_id: str | None = Header(default=None),
):
    with observation(
        "retrieval.search",
        trace_id=x_langfuse_trace_id,
        parent_span_id=x_langfuse_parent_id,
        input=request.model_dump(),
        metadata={"reranker_enabled": str(request.rerank).lower()},
    ) as span:
        response = _search_documents(request)
        span.update(output=response)
        return response


@app.post("/filter")
async def filter_docs(request: SearchFilterRequest):
    """
    Retrieves document chunks based on exact metadata matches without performing vector search.

    This endpoint utilizes Qdrant's scroll API to filter records by document_id, 
    and optionally by content type and section. It is designed for deterministic 
    data retrieval rather than semantic similarity matching.

    Args:
    request (SearchFilterRequest): The filtering criteria containing the mandatory 
                                    document_id, and optional type, section, and limit.

    Returns:
    dict: A dictionary containing:
        - results (list): A formatted list of matching chunks with their text and metadata.
    """
    try:
        # Build the exact-match conditions
        must_conditions = [
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=request.document_id)
            )
        ]

        if request.type:
            must_conditions.append(
                models.FieldCondition(
                    key="type",
                    match=models.MatchValue(value=request.type)
                )
            )

        if request.section:
            must_conditions.append(
                models.FieldCondition(
                    key="section",
                    match=models.MatchValue(value=request.section)
                )
            )

        # Use Qdrant's scroll API instead of search
        # Scroll is designed specifically for metadata filtering without vectors
        records, next_page_offset = qdrant_client.scroll(
            collection_name="financials",
            scroll_filter=models.Filter(must=must_conditions),
            limit=request.limit,
            with_payload=True,
            with_vectors=False # Saves bandwidth by not returning the 384-dimensional arrays
        )

        formatted_results = []
        for record in records:
            formatted_results.append({
                "text": record.payload.get("text"),
                "metadata": {
                    "document_id": record.payload.get("document_id"),
                    "source_filename": record.payload.get("source_filename"),
                    "page_number": record.payload.get("page_number"),
                    "section": record.payload.get("section"),
                    "type": record.payload.get("type")
                }
            })

        # Returns a dict, cause it can be useful to add more keys to it in the future
        return {
            "results": formatted_results,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8002,
    )
