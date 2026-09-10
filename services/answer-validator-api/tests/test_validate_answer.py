from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_valid_calculated_answer_succeeds():
    payload = {
        "answer_type": "calculated",
        "evidence": [{"document_id": "doc_041", "page": 2, "section": "Operating Expenses"}],
        "params": {"value": 13.4, "formula": "(3875-3410)/3410*100"},
    }
    response = client.post("/validate_answer", json=payload)
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_missing_evidence_is_rejected():
    payload = {
        "answer_type": "direct",
        "evidence": [],
        "params": {"value": "$142.5M"},
    }
    response = client.post("/validate_answer", json=payload)
    body = response.json()
    assert body["valid"] is False
    assert body["reason"] == "Missing required evidence citation."


def test_missing_type_specific_key_is_rejected():
    payload = {
        "answer_type": "calculated",
        "evidence": [{"document_id": "doc_041", "page": 2}],
        "params": {"value": 13.4},  # formula deliberately missing
    }
    response = client.post("/validate_answer", json=payload)
    body = response.json()
    assert body["valid"] is False
    assert body["reason"] == "Missing required key 'formula'"


def test_insufficient_evidence_allows_empty_evidence():
    payload = {
        "answer_type": "insufficient_evidence",
        "evidence": [],
        "params": {"reason": "No document in the indexed corpus reports restructuring expenses."},
    }
    response = client.post("/validate_answer", json=payload)
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_unknown_answer_type_is_rejected():
    payload = {"answer_type": "not_a_real_type", "evidence": [], "params": {}}
    response = client.post("/validate_answer", json=payload)
    body = response.json()
    assert body["valid"] is False
    assert "Unknown or missing answer_type" in body["reason"]