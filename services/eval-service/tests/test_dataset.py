import json
import uuid
from pathlib import Path

import pytest

from app.dataset import build_manifest, load_tat_dqa


@pytest.fixture
def source_path():
    path = Path(__file__).parent / f"generated-{uuid.uuid4().hex}.json"
    yield path
    path.unlink(missing_ok=True)


def test_loads_flat_practice_format(source_path):
    source = source_path
    source.write_text(
        json.dumps(
            [
                {
                    "question_id": "A1",
                    "question_text": "What was revenue?",
                    "ground_truth_answer": 42,
                    "answer_type": "arithmetic",
                    "scale": "million",
                    "is_answerable": True,
                    "gold_evidence": [
                        {
                            "source_doc_uid": "doc-1",
                            "source_document": "report.pdf",
                            "source_page": 1,
                            "gold_facts": ["42"],
                            "evidence_block_uuids": ["block-1"],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    item = load_tat_dqa(source)[0]
    assert item.question_id == "A1"
    assert item.document_ids == ["doc-1"]
    assert item.gold_evidence[0].block_ids == ["block-1"]


def test_loads_official_nested_format(source_path):
    source = source_path
    source.write_text(
        json.dumps(
            [
                {
                    "doc": {"uid": "doc-1", "source": "annual.pdf", "page": 3},
                    "questions": [
                        {
                            "uid": "q-1",
                            "question": "Which year?",
                            "answer": ["2020"],
                            "answer_type": "span",
                            "scale": "",
                            "facts": ["2020"],
                            "block_mapping": [{"block-7": [0, 4]}],
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    item = load_tat_dqa(source)[0]
    assert item.question == "Which year?"
    assert item.document_ids == ["doc-1"]
    assert item.gold_evidence[0].page == 3
    assert item.gold_evidence[0].block_ids == ["block-7"]


def test_manifest_is_deterministic_and_keeps_connected_documents_together(source_path):
    source = source_path
    rows = []
    for question_id, docs in [("q1", ["a", "b"]), ("q2", ["b"]), ("q3", ["c"])]:
        rows.append(
            {
                "question_id": question_id,
                "question_text": question_id,
                "ground_truth_answer": "x",
                "answer_type": "span",
                "scale": "",
                "gold_evidence": [
                    {"source_doc_uid": doc, "source_page": 1} for doc in docs
                ],
            }
        )
    source.write_text(json.dumps(rows), encoding="utf-8")
    first = build_manifest(source, name="x", seed=7, selection_fraction=0.5)
    second = build_manifest(source, name="x", seed=7, selection_fraction=0.5)
    assert first.manifest_id == second.manifest_id
    selected = {item.question_id for item in first.items}
    assert ("q1" in selected) == ("q2" in selected)
