from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.graph import graph
from app.telemetry import as_dict, telemetry_scope

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
    include_diagnostics: bool = False
    evaluation_variant: Literal["reranker_on", "reranker_off"] = "reranker_on"
    request_id: str | None = None
    trace_id: str | None = None
    parent_span_id: str | None = None


class AskResponse(BaseModel):
    answer_type: str
    evidence: list
    params: dict


@app.get("/health")
def health() -> dict:
    """Liveness check endpoint."""
    return {"status": "ok", "service": "agent-service"}


@app.post("/ask")
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
        with telemetry_scope(
            request.evaluation_variant,
            trace_id=request.trace_id,
            parent_span_id=request.parent_span_id,
            question=request.question,
            request_id=request.request_id,
        ) as telemetry:
            result = graph.invoke(initial_state)
            diagnostics = as_dict(telemetry)
    except Exception as e:
        # Unexpected pipeline error (e.g. retrieval-api connection failure)
        raise HTTPException(status_code=500, detail=f"agent pipeline error: {e}")

    answer = result.get("answer") or {
        "answer_type": "insufficient_evidence",
        "evidence": [],
        "params": {"reason": "Agent did not produce an answer"},
    }
    if request.include_diagnostics:
        diagnostics.update(
            {
                "request_id": request.request_id,
                "trace_id": request.trace_id,
                "question_type": result.get("question_type"),
                "retries": result.get("retries", 0),
                "selected_evidence": result.get("evidence") or [],
            }
        )
        return {"answer": answer, "diagnostics": diagnostics}
    return AskResponse.model_validate(answer).model_dump()


if __name__ == "__main__":
    import uvicorn
    # Run directly: uvicorn app.main:app --reload --port 8003
    uvicorn.run("app.main:app", host="0.0.0.0", port=8003, reload=True)
