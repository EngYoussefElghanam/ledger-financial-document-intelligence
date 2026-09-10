from fastapi.testclient import TestClient

import app.main as main_module

client = TestClient(main_module.app)


async def _fake_ask_agent(question, document_id=None, **kwargs):
    return {
        "answer_type": "direct",
        "evidence": [{"document_id": "doc_017", "page": 1}],
        "params": {"value": "$142.5M"},
    }


async def _fake_validate_valid(answer, **kwargs):
    return {"valid": True, "answer": answer}


async def _fake_validate_invalid(answer, **kwargs):
    if answer["answer_type"] == "insufficient_evidence":
        return {"valid": True, "answer": answer}
    return {"valid": False, "reason": "Missing required key 'formula'"}


def test_ask_returns_agent_answer_when_valid(monkeypatch):
    monkeypatch.setattr(main_module, "ask_agent", _fake_ask_agent)
    monkeypatch.setattr(main_module, "validate", _fake_validate_valid)

    response = client.post("/ask", json={"question": "What was operating income?"})

    assert response.status_code == 200
    assert response.json()["answer_type"] == "direct"


def test_ask_falls_back_to_insufficient_evidence_when_invalid(monkeypatch):
    monkeypatch.setattr(main_module, "ask_agent", _fake_ask_agent)
    monkeypatch.setattr(main_module, "validate", _fake_validate_invalid)

    response = client.post("/ask", json={"question": "What was operating income?"})
    body = response.json()

    assert body["answer_type"] == "insufficient_evidence"
    assert "failed validation" in body["params"]["reason"]
