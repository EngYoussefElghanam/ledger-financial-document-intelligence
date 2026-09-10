"""HTTP client for the live agent /ask contract."""
import httpx
from app.config import AGENT_SERVICE_URL, USE_MOCK_AGENT
from app.http_client import get_client


class AgentDependencyError(RuntimeError):
    pass


async def ask_agent(
    question: str,
    document_id: str | None = None,
    *,
    include_diagnostics: bool = False,
    evaluation_variant: str = "reranker_on",
    request_id: str | None = None,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
) -> dict:
    if USE_MOCK_AGENT:
        answer = {
            "answer_type": "insufficient_evidence",
            "evidence": [],
            "params": {"reason": "MOCK AGENT enabled; no document search was performed."},
        }
        return {"answer": answer, "diagnostics": {"mock": True}} if include_diagnostics else answer
    try:
        response = await get_client().post(
            f"{AGENT_SERVICE_URL}/ask",
            json={
                "question": question,
                "document_id": document_id,
                "include_diagnostics": include_diagnostics,
                "evaluation_variant": evaluation_variant,
                "request_id": request_id,
                "trace_id": trace_id,
                "parent_span_id": parent_span_id,
            },
            timeout=60,
        )
        response.raise_for_status()
        answer = response.json()
        if not isinstance(answer, dict):
            raise ValueError("agent returned a non-object answer")
        return answer
    except (httpx.HTTPError, ValueError) as exc:
        raise AgentDependencyError("agent-service request failed") from exc
