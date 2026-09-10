"""Retrieval metrics with explicit relevance granularity and coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.models import GoldEvidence


def _stem(value: str | None) -> str:
    return Path(value or "").stem.lower()


def _doc_aliases(evidence: GoldEvidence) -> set[str]:
    return {_stem(evidence.document_id), _stem(evidence.source_document)} - {""}


def _result_doc(result: dict[str, Any]) -> str:
    metadata = result.get("metadata") or {}
    return _stem(metadata.get("document_id") or result.get("document_id"))


def _select_level(
    evidence: list[GoldEvidence], results: list[dict[str, Any]]
) -> str:
    gold_blocks = {block for item in evidence for block in item.block_ids}
    returned_blocks = {
        str(result.get("chunk_id") or (result.get("metadata") or {}).get("chunk_id"))
        for result in results
        if result.get("chunk_id") or (result.get("metadata") or {}).get("chunk_id")
    }
    # Dataset UUIDs and Docling IDs are different namespaces. Only use chunk
    # scoring after an explicit alignment; otherwise score known pages/docs.
    if gold_blocks and returned_blocks and all(
        (result.get("metadata") or {}).get("gold_block_ids_aligned") is True
        for result in results
    ):
        return "chunk"
    if any(item.page is not None for item in evidence):
        return "page"
    if evidence:
        return "document"
    return "unavailable"


def _key_for_result(result: dict[str, Any], level: str) -> Any:
    metadata = result.get("metadata") or {}
    if level == "chunk":
        return str(result.get("chunk_id") or metadata.get("chunk_id"))
    if level == "page":
        return (
            _result_doc(result),
            metadata.get("page_number")
            or result.get("page_number")
            or result.get("page"),
        )
    return _result_doc(result)


def score_retrieval(
    evidence: list[GoldEvidence],
    results: list[dict[str, Any]],
    k_values: list[int],
) -> dict[str, Any]:
    level = _select_level(evidence, results)
    if level == "unavailable":
        return {"mapping_level": level, "mapping_coverage": 0.0, "metrics_by_k": {}}
    relevant: set[Any] = set()
    aliases = {
        alias: _stem(item.document_id)
        for item in evidence for alias in _doc_aliases(item)
    }
    for item in evidence:
        if level == "page" and item.page is not None:
            relevant.add((_stem(item.document_id), item.page))
        elif level == "document":
            relevant.add(_stem(item.document_id))
        elif level == "chunk":
            relevant.update(item.block_ids)
    ranked = [_key_for_result(result, level) for result in results]
    if level == "page":
        ranked = [(aliases.get(doc, doc), page) for doc, page in ranked]
    elif level == "document":
        ranked = [aliases.get(doc, doc) for doc in ranked]
    first_rank = next((index + 1 for index, key in enumerate(ranked) if key in relevant), None)
    metrics: dict[str, dict[str, float]] = {}
    for k in sorted(set(k_values)):
        hits = len(relevant.intersection(ranked[:k]))
        metrics[str(k)] = {
            "recall": hits / len(relevant) if relevant else 0.0,
            "precision": hits / k,
            "hit_rate": float(hits > 0),
            "mrr": 1.0 / first_rank if first_rank is not None and first_rank <= k else 0.0,
        }
    return {
        "mapping_level": level,
        "mapping_coverage": 1.0,
        "relevant_count": len(relevant),
        "returned_count": len(ranked),
        "metrics_by_k": metrics,
    }
