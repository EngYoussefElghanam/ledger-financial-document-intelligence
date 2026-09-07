from fastembed import TextEmbedding, SparseTextEmbedding
from sentence_transformers import CrossEncoder

# Semantic model (outputs a 384-dimensional vector)
dense_model = TextEmbedding("BAAI/bge-small-en-v1.5")
# Keyword matching model
sparse_model = SparseTextEmbedding("Qdrant/bm25")

reranker_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


# This funtion used to take a single string and output an embedding vector of this string
# Then using a for loop the code would loop through all chunks and embed them 1 by 1
# While this was a correct implementation it can be made faster using parallelization
# Instead of passing each string 1by1, we pass them all at once, and fastembed itself has-
# inner support for parallelization
# Returns a list of vector embeddings of the text
def get_dense_vectors(texts: list[str]):
    return list(dense_model.embed(texts))

# Same comments for get_dense_vector except for the return type
# It returns an iterable containing SparseEmbedding object
def get_sparse_vectors(texts: list[str]):
    # Returns an object with explicit vocabulary indices and their importance values
    return list(sparse_model.embed(texts))

def get_rerank_scores(query: str, chunks: list[str]) -> list[float]:
    pairs = [[query, chunk] for chunk in chunks]

    return reranker_model.predict(pairs).tolist()