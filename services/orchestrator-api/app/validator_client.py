"""Submit candidate answers to the answer validator."""
import httpx
from app.config import ANSWER_VALIDATOR_URL


async def validate(answer: dict) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{ANSWER_VALIDATOR_URL}/validate_answer", json=answer, timeout=10
        )
        response.raise_for_status()
        return response.json()
