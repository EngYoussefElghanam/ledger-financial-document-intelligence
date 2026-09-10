"""Submit candidate answers to the answer validator."""
import httpx
from app.config import ANSWER_VALIDATOR_URL


async def validate(
    answer: dict,
    *,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
) -> dict:
    headers = {}
    if trace_id:
        headers["X-Langfuse-Trace-ID"] = trace_id
    if parent_span_id:
        headers["X-Langfuse-Parent-ID"] = parent_span_id
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ANSWER_VALIDATOR_URL}/validate_answer",
            json=answer,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
