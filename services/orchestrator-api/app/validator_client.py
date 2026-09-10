"""Submit candidate answers to the answer validator."""
from app.config import ANSWER_VALIDATOR_URL
from app.http_client import get_client


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
    response = await get_client().post(
        f"{ANSWER_VALIDATOR_URL}/validate_answer",
        json=answer,
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
