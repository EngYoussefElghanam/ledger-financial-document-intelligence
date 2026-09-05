import re
import httpx
import numexpr
from langchain_core.tools import tool

RETRIEVAL_API_URL = "http://localhost:8000"


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
def search_documents(query: str, document_id: str = None, limit: int = 5) -> list:
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
def search_tables(query: str, document_id: str = None, limit: int = 5) -> list:
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
def filter_documents(document_id: str = None, section: str = None, content_type: str = None) -> list:
    """
    Filter and list indexed document chunks by metadata, without a search query.
    Use this when the question is about a specific document, section, or
    content type (e.g. "show me all tables in document X") rather than a
    semantic search.

    Args:
        document_id: Optional - restrict to one specific document.
        section: Optional - restrict to a specific section name.
        content_type: Optional - "text" or "table".
    """
    payload = {"query": section or "financial data", "limit": 20}
    if document_id:
        payload["document_id"] = document_id

    try:
        response = httpx.post(f"{RETRIEVAL_API_URL}/search", json=payload, timeout=30)
        response.raise_for_status()
        results = response.json()["results"]
    except Exception as e:
        return [{"error": str(e)}]

    if content_type:
        results = [r for r in results if r.get("metadata", {}).get("type") == content_type]
    if section:
        results = [r for r in results if r.get("metadata", {}).get("section", "").lower() == section.lower()]

    return results