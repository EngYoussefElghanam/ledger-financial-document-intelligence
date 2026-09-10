import re
import httpx
import numexpr
from langchain_core.tools import tool
from typing import Optional

from app.config import RETRIEVAL_API_URL
from app.telemetry import record_retrieval, reranker_enabled
from ledger_observability import observation, outbound_trace_headers

@tool
def calculate(expression: str) -> dict:
    """
    Safely evaluates a math expression (handles $ signs, commas, abs()).
    Always use this tool for any arithmetic - never compute math directly.

    Args:
        expression: A math expression as a string, e.g. "abs(9447-314258)"
                    or "(25282320-22095416)/22095416"
    """
    with observation("calculate", as_type="tool", input={"expression": expression}) as span:
        try:
            cleaned = re.sub(r'[\$,]', '', expression)
            result = float(numexpr.evaluate(cleaned))
            output = {"success": True, "result": result, "expression": expression}
        except Exception as e:
            output = {"success": False, "error": str(e), "expression": expression}
        span.update(output=output)
        return output


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
    payload = {
        "query": query,
        "limit": limit,
        "rerank": reranker_enabled(),
        "include_diagnostics": True,
    }
    if document_id:
        payload["document_id"] = document_id

    try:
        response = httpx.post(
            f"{RETRIEVAL_API_URL}/search",
            json=payload,
            headers=outbound_trace_headers(),
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        record_retrieval(payload, body)
        return body["results"]
    except Exception as e:
        raise RuntimeError("retrieval-api request failed") from e


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
    payload = {
        "query": query,
        "document_id": document_id,
        "limit": limit,
        "content_type": "table",
        "rerank": reranker_enabled(),
        "include_diagnostics": True,
    }
    try:
        response = httpx.post(
            f"{RETRIEVAL_API_URL}/search",
            json=payload,
            headers=outbound_trace_headers(),
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        record_retrieval(payload, body)
        return body["results"]
    except Exception as e:
        raise RuntimeError("retrieval-api request failed") from e


@tool
def filter_documents(document_id: Optional[str] = None, section: Optional[str] = None, content_type: Optional[str] = None) -> list:
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
    payload = {
        "query": section or "financial data",
        "limit": 20,
        "section": section,
        "content_type": content_type,
        "rerank": reranker_enabled(),
        "include_diagnostics": True,
    }
    if document_id:
        payload["document_id"] = document_id

    try:
        response = httpx.post(
            f"{RETRIEVAL_API_URL}/search",
            json=payload,
            headers=outbound_trace_headers(),
            timeout=30,
        )
        response.raise_for_status()
        body = response.json()
        record_retrieval(payload, body)
        results = body["results"]
    except Exception as e:
        raise RuntimeError("retrieval-api request failed") from e

    return results
