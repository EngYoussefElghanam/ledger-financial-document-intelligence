"""Client for answer-validator-api: the one downstream service that's
actually real and running so far"""

from app.config import ANSWER_VALIDATOR_URL
from app.http_client import get_client


async def validate(answer: dict) -> dict:
    client = get_client()
    resp = await client.post(
        f"{ANSWER_VALIDATOR_URL}/validate_answer",
        json=answer,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()