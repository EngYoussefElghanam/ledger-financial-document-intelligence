"""Live PDF-to-answer smoke test for an already running real stack."""

import argparse
from pathlib import Path

import httpx


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("question")
    parser.add_argument("second_question")
    parser.add_argument("--orchestrator-url", default="http://localhost:8000")
    args = parser.parse_args()

    health = httpx.get(f"{args.orchestrator_url}/health", timeout=10)
    health.raise_for_status()
    assert health.json().get("mock_agent") is False, "orchestrator is using mock agent"

    with args.pdf.open("rb") as stream:
        ingest = httpx.post(
            f"{args.orchestrator_url}/documents/ingest",
            files={"file": (args.pdf.name, stream, "application/pdf")},
            timeout=600,
        )
    ingest.raise_for_status()
    document_id = ingest.json()["document_id"]

    answers = []
    for question in (args.question, args.second_question):
        response = httpx.post(
            f"{args.orchestrator_url}/ask",
            json={"question": question, "document_id": document_id},
            timeout=180,
        )
        response.raise_for_status()
        answer = response.json()
        evidence_items = answer.get("evidence", [])
        assert evidence_items, f"No evidence returned for: {question}"
        for evidence in evidence_items:
            assert evidence["document_id"] == document_id
        answers.append(answer)

    assert answers[0] != answers[1], "Changing the question returned an identical answer"
    print({"document_id": document_id, "answers": answers})


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        raise SystemExit(f"Live smoke test could not reach a healthy stack: {exc}") from exc
