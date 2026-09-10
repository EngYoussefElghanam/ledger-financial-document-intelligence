from app.metrics.retrieval import score_retrieval
from app.models import GoldEvidence


def result(doc, page, chunk):
    return {
        "chunk_id": chunk,
        "metadata": {"document_id": doc, "page_number": page, "gold_block_ids_aligned": True},
    }


def test_page_metrics_with_two_relevant_documents():
    evidence = [
        GoldEvidence(document_id="doc-a", page=1),
        GoldEvidence(document_id="doc-b", page=1),
    ]
    metrics = score_retrieval(
        evidence,
        [result("wrong", 1, "x"), result("doc-a", 1, "y"), result("doc-b", 1, "z")],
        [1, 3],
    )
    assert metrics["mapping_level"] == "page"
    assert metrics["metrics_by_k"]["1"]["hit_rate"] == 0
    assert metrics["metrics_by_k"]["3"]["recall"] == 1
    assert metrics["metrics_by_k"]["3"]["precision"] == 2 / 3
    assert metrics["metrics_by_k"]["3"]["mrr"] == 0.5


def test_chunk_metrics_when_ids_are_aligned():
    evidence = [GoldEvidence(document_id="doc", block_ids=["gold-block"])]
    metrics = score_retrieval(evidence, [result("doc", 1, "gold-block")], [1])
    assert metrics["mapping_level"] == "chunk"
    assert metrics["metrics_by_k"]["1"]["recall"] == 1


def test_chunk_miss_does_not_fall_back_to_page_match():
    evidence = [GoldEvidence(document_id="doc", page=1, block_ids=["gold-block"])]
    metrics = score_retrieval(evidence, [result("doc", 1, "wrong-block")], [1])
    assert metrics["mapping_level"] == "chunk"
    assert metrics["metrics_by_k"]["1"]["hit_rate"] == 0


def test_flat_candidate_diagnostics_support_page_metrics():
    evidence = [GoldEvidence(document_id="doc-a", page=2)]
    candidate = {"chunk_id": "candidate-1", "document_id": "doc-a", "page_number": 2}
    metrics = score_retrieval(evidence, [candidate], [1])
    assert metrics["mapping_level"] == "page"
    assert metrics["metrics_by_k"]["1"]["hit_rate"] == 1


def test_unavailable_mapping_has_zero_coverage():
    metrics = score_retrieval([], [result("doc", 1, "chunk")], [1])
    assert metrics["mapping_level"] == "unavailable"
    assert metrics["mapping_coverage"] == 0
    assert metrics["metrics_by_k"] == {}


def test_docling_ids_use_page_mapping_and_alias_is_not_extra_gold():
    evidence = [GoldEvidence(document_id="uid", source_document="report.pdf", page=1,
                             block_ids=["tat-dqa-block"])]
    found = {"chunk_id": "docling-block", "metadata": {"document_id": "uid", "page_number": 1}}
    metrics = score_retrieval(evidence, [found], [1])
    assert metrics["mapping_level"] == "page"
    assert metrics["relevant_count"] == 1
    assert metrics["metrics_by_k"]["1"]["recall"] == 1
