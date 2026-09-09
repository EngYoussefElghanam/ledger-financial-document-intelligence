from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.graph import graph

app = FastAPI(
    title="agent-service",
    description="LEDGER reasoning agent — classifies questions, retrieves evidence, "
                "verifies sufficiency, calculates when needed, and returns a "
                "strict schema-compliant answer.",
    version="0.1.0",
)


class AskRequest(BaseModel):
    question: str
    document_id: Optional[str] = None  # Optional: target a specific document, otherwise searches across the entire corpus


class AskResponse(BaseModel):
    answer_type: str
    evidence: list
    params: dict


@app.get("/health")
def health() -> dict:
    """Liveness check endpoint."""
    return {"status": "ok", "service": "agent-service"}


@app.post("/ask", response_model=AskResponse)
@app.post("/answer", response_model=AskResponse)
def ask(request: AskRequest):
    """
    Main entrypoint: accepts a question (and optional document_id),
    executes the full LangGraph reasoning pipeline, and returns
    a strict-schema compliant answer.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    initial_state = {
        "question": request.question,
        "document_id": request.document_id,
        "question_type": "text",
        "evidence": [],
        "is_sufficient": False,
        "retries": 0,
        "calculation": None,
        "answer": {},
    }

    try:
        result = graph.invoke(initial_state)
    except Exception as e:
        # Unexpected pipeline error (e.g. retrieval-api connection failure)
        raise HTTPException(status_code=500, detail=f"agent pipeline error: {e}")

    answer = result.get("answer") or {
        "answer_type": "insufficient_evidence",
        "evidence": [],
        "params": {"reason": "Agent did not produce an answer"},
    }
    return answer


if __name__ == "__main__":
    import uvicorn
    # Run directly: uvicorn app.main:app --reload --port 8003
    uvicorn.run("app.main:app", host="0.0.0.0", port=8003, reload=True)