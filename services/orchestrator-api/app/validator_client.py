"""Client for answer-validator-api: the one downstream service that's
actually real and running so far"""

import httpx

from app.config import ANSWER_VALIDATOR_URL


async def validate(answer: dict) -> dict:
    """Returns the validator's response dict: {"valid": bool, ...}."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{ANSWER_VALIDATOR_URL}/validate_answer",
            json=answer,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()