import os
import re
import httpx
import numexpr
from langchain_core.tools import tool
from typing import Optional


RETRIEVAL_API_URL = os.getenv("RETRIEVAL_API_URL", "http://localhost:8000")


@tool
def calculate(expression: str) -> dict:
    """
    Safely evaluates a math expression (handles $ signs, commas, abs()).
    Always use this tool for any arithmetic - never compute math directly.

    Args:
        expression: A math expression as a string, e.g. "abs(9447-314258)"
                    or "(25282320-22095416)/22095416"
    """
    try:
        cleaned = re.sub(r'[\$,]', '', expression)
        result = float(numexpr.evaluate(cleaned))
        return {"success": True, "result": result, "expression": expression}
    except Exception as e:
        return {"success": False, "error": str(e), "expression": expression}


@tool
def search_documents(query: str, document_id: Optional[str] = None, limit: int = 5) -> list:
    """
    Search across financial documents for relevant text and table chunks.
    Use this for text-based or general questions before answering.

    Args:
        query: The search query text.
        document_id: Optional - restrict search to one specific document.
        limit: Number of results to return (default 5).
    """
    payload = {"query": query, "limit": limit}
    if document_id:
        payload["document_id"] = document_id

    try:
        response = httpx.post(f"{RETRIEVAL_API_URL}/search", json=payload, timeout=30)
        response.raise_for_status()
        return response.json()["results"]
    except Exception as e:
        return [{"error": str(e)}]


@tool
def search_tables(query: str, document_id: Optional[str] = None, limit: int = 5) -> list:
    """
    Search specifically for table chunks relevant to the query.
    Use this when the question requires data from a financial table.

    Args:
        query: The search query text.
        document_id: Optional - restrict search to one specific document.
        limit: Number of results to return (default 5).
    """
    results = search_documents.invoke({"query": query, "document_id": document_id, "limit": limit})
    if results and "error" in results[0]:
        return results
    return [r for r in results if r.get("metadata", {}).get("type") == "table"]


@tool
def filter_documents(document_id: str, content_type: Optional[str] = None, section: Optional[str] = None, limit: int = 50) -> list:
    """
    Retrieve document chunks based on exact metadata matches without vector search.
    Calls the dedicated non-vector POST /filter endpoint on retrieval-api.

    Args:
        document_id: The exact ID of the target document (Required).
        content_type: Optional - filter by "table" or "text".
        section: Optional - filter by section title.
        limit: Max chunks to return (default 50).
    """
    payload = {"document_id": document_id, "limit": limit}
    if content_type:
        payload["type"] = content_type
    if section:
        payload["section"] = section

    try:
        response = httpx.post(f"{RETRIEVAL_API_URL}/filter", json=payload, timeout=30)
        response.raise_for_status()
        return response.json().get("results", [])
    except Exception as e:
        return [{"error": str(e)}]