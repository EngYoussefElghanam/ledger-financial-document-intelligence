from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers import CrossEncoder

# Semantic model (outputs a 384-dimensional vector)
dense_model = TextEmbedding("BAAI/bge-small-en-v1.5")
# Keyword matching model
sparse_model = SparseTextEmbedding("Qdrant/bm25")

reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

def get_dense_vector(text: str) -> list[float]:
    return list(dense_model.embed([text]))[0].tolist()

def get_sparse_vector(text: str):
    # Returns an object with explicit vocabulary indices and their importance values
    sparse_result = list(sparse_model.embed([text]))[0]
    return {
        "indices": sparse_result.indices.tolist(), 
        "values": sparse_result.values.tolist()
    }

def get_rerank_scores(query: str, chunks: list[str]) -> list[float]:
    pairs = [[query, chunk] for chunk in chunks]

    return reranker_model.predict(pairs).tolist()