"""
answer-validator-api: the single source of truth for what constitutes a
valid, grounded answer. Accepts raw JSON (not an auto-parsed Pydantic
model) so we can produce the spec's exact log message formats instead of
FastAPI's generic 422 errors.
"""

from fastapi import FastAPI, Body
from pydantic import ValidationError

from schemas.answer import (
    DirectAnswer,
    CalculatedAnswer,
    MultiSpanAnswer,
    InsufficientEvidenceAnswer,
)

app = FastAPI(title="answer-validator-api")

ANSWER_MODELS = {
    "direct": DirectAnswer,
    "calculated": CalculatedAnswer,
    "multi_span": MultiSpanAnswer,
    "insufficient_evidence": InsufficientEvidenceAnswer,
}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/validate_answer")
def validate_answer(payload: dict = Body(...)) -> dict:
    answer_type = payload.get("answer_type")

    # Check 1: is answer_type one we recognize at all? 
    if answer_type not in ANSWER_MODELS:
        reason = f"Unknown or missing answer_type '{answer_type}'"
        print(f"[ANSWER-VALIDATOR-ERROR] Invalid answer. Reason: {reason}")
        return {"valid": False, "reason": reason}

    # Check 2: the evidence-citation rule, shared across 3 of the 4 types 
    # insufficient_evidence is the one type allowed to have empty evidence,
    # so it's explicitly excluded from this check.
    if answer_type != "insufficient_evidence" and not payload.get("evidence"):
        reason = "Missing required evidence citation."
        print(f"[ANSWER-VALIDATOR-ERROR] Invalid answer. Reason: {reason}")
        return {"valid": False, "reason": reason}

    # Check 3: full shape validation via the Pydantic model ---
    model_cls = ANSWER_MODELS[answer_type]
    try:
        validated = model_cls(**payload)
    except ValidationError as e:
        missing_key = _first_missing_key(e)
        if missing_key:
            reason = f"Missing required key '{missing_key}'"
        else:
            # Fallback for issues that aren't a missing field (e.g. wrong
            # type — value should be a number but got a string).
            reason = e.errors()[0]["msg"]
        print(f"[ANSWER-VALIDATOR-ERROR] Invalid answer for '{answer_type}': {reason}")
        return {"valid": False, "reason": reason}

    # Success: log per spec, referencing only the first evidence entry 
    if validated.evidence:
        first = validated.evidence[0]
        evidence_log = {"document_id": first.document_id, "page": first.page}
    else:
        evidence_log = {}
    # This only logs first evidence as shown in the project specification
    # Can later be modified t include all evidence
    print(
        f"[ANSWER-VALIDATOR-SUCCESS] Received and validated answer of type "
        f"'{answer_type}' with evidence {evidence_log}"
    )
    return {"valid": True, "answer": validated.model_dump()}


def _first_missing_key(e: ValidationError) -> str | None:
    """Pull out the field name of the first 'required field missing' error,
    e.g. loc=('params', 'formula') -> 'formula'. Returns None if the
    validation error was something other than a missing field."""
    for err in e.errors():
        if err["type"] == "missing":
            return err["loc"][-1]
    return None