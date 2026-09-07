from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.graph import graph

app = FastAPI(
    title="agent-service",
    description="LEDGER reasoning agent — classifies the question, retrieves evidence, "
                "verifies sufficiency, calculates when needed, and returns a "
                "schema-compliant answer.",
    version="0.1.0",
)


class AskRequest(BaseModel):
    question: str
    document_id: Optional[str] = None  # اختياري: تحديد مستند بعينه، وإلا بحث على الـcorpus كله


class AskResponse(BaseModel):
    answer_type: str
    evidence: list
    params: dict


@app.get("/health")
def health():
    return {"status": "ok", "service": "agent-service"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    """
    نقطة الدخول الرئيسية: بتاخد سؤال (وممكن document_id اختياري)،
    وبتشغّل الـLangGraph pipeline كامل، وبترجع answer متوافق مع الـstrict schema.
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
        # لو حصل خطأ غير متوقع في الـpipeline نفسه (زي انقطاع retrieval-api)
        raise HTTPException(status_code=500, detail=f"agent pipeline error: {e}")

    answer = result.get("answer") or {
        "answer_type": "insufficient_evidence",
        "evidence": [],
        "params": {"reason": "Agent did not produce an answer"},
    }
    return answer


if __name__ == "__main__":
    import uvicorn
    # شغّلها بـ: python -m app.main  (أو uvicorn app.main:app --reload --port 8003)
    uvicorn.run("app.main:app", host="0.0.0.0", port=8003, reload=True)