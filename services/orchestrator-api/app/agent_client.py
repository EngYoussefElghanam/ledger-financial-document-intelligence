"""HTTP client for the live agent /ask contract."""
import httpx
from app.config import AGENT_SERVICE_URL, USE_MOCK_AGENT


class AgentDependencyError(RuntimeError):
    pass


async def ask_agent(question: str, document_id: str | None = None) -> dict:
    if USE_MOCK_AGENT:
        return {
            "answer_type": "insufficient_evidence",
            "evidence": [],
            "params": {"reason": "MOCK AGENT enabled; no document search was performed."},
        }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AGENT_SERVICE_URL}/ask",
                json={"question": question, "document_id": document_id},
                timeout=60,
            )
            response.raise_for_status()
            answer = response.json()
            if not isinstance(answer, dict):
                raise ValueError("agent returned a non-object answer")
            return answer
    except (httpx.HTTPError, ValueError) as exc:
        raise AgentDependencyError("agent-service request failed") from exc
