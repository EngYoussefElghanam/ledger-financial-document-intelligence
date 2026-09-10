"""Load official and extended flat TAT-DQA annotations into one contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.models import DatasetManifest, EvaluationItem, GoldEvidence


VALID_SCALES = {"", "thousand", "million", "billion", "percent"}
ROOT_DIR = Path(__file__).resolve().parents[3]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean_scale(value: Any) -> str:
    scale = str(value or "").strip().lower()
    if scale in {"none", "null"}:
        scale = ""
    if scale not in VALID_SCALES:
        raise ValueError(f"unsupported TAT-DQA scale {value!r}")
    return scale


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _flat_evidence(row: dict[str, Any]) -> list[GoldEvidence]:
    result: list[GoldEvidence] = []
    for evidence in row.get("gold_evidence") or []:
        doc_id = evidence.get("source_doc_uid") or evidence.get("source_document")
        if not doc_id:
            continue
        result.append(
            GoldEvidence(
                document_id=str(doc_id),
                source_document=evidence.get("source_document"),
                page=evidence.get("source_page"),
                content_type=evidence.get("content_type"),
                facts=[str(value) for value in evidence.get("gold_facts") or []],
                block_ids=[str(value) for value in evidence.get("evidence_block_uuids") or []],
            )
        )
    return result


def _load_flat(rows: list[dict[str, Any]]) -> list[EvaluationItem]:
    items: list[EvaluationItem] = []
    for row in rows:
        evidence = _flat_evidence(row)
        document_ids = list(dict.fromkeys(e.document_id for e in evidence))
        fallback_doc = row.get("source_doc_uid") or row.get("source_document")
        if fallback_doc and fallback_doc not in document_ids:
            document_ids.append(str(fallback_doc))
        reserved = {
            "question_id", "question_text", "ground_truth_answer", "answer_type",
            "scale", "is_answerable", "gold_evidence", "source_doc_uid",
            "source_document",
        }
        items.append(
            EvaluationItem(
                question_id=str(row["question_id"]),
                question=str(row["question_text"]),
                gold_answer=row.get("ground_truth_answer"),
                answer_type=str(row.get("answer_type") or "span"),
                scale=_clean_scale(row.get("scale")),
                is_answerable=bool(row.get("is_answerable", True)),
                document_ids=document_ids,
                gold_evidence=evidence,
                metadata={key: value for key, value in row.items() if key not in reserved},
            )
        )
    return items


def _official_evidence(doc: dict[str, Any], question: dict[str, Any]) -> list[GoldEvidence]:
    doc_id = str(doc.get("uid") or doc.get("source") or "")
    if not doc_id:
        return []
    block_ids: list[str] = []
    for mapping in question.get("block_mapping") or []:
        if isinstance(mapping, dict):
            block_ids.extend(str(key) for key in mapping)
    return [
        GoldEvidence(
            document_id=doc_id,
            source_document=doc.get("source"),
            page=doc.get("page"),
            facts=[str(value) for value in question.get("facts") or []],
            block_ids=block_ids,
        )
    ]


def _load_official(rows: list[dict[str, Any]]) -> list[EvaluationItem]:
    items: list[EvaluationItem] = []
    for group in rows:
        doc = group.get("doc") or {}
        for question in group.get("questions") or []:
            evidence = _official_evidence(doc, question)
            items.append(
                EvaluationItem(
                    question_id=str(question["uid"]),
                    question=str(question["question"]),
                    gold_answer=question.get("answer"),
                    answer_type=str(question.get("answer_type") or "span"),
                    scale=_clean_scale(question.get("scale")),
                    document_ids=[evidence[0].document_id] if evidence else [],
                    gold_evidence=evidence,
                    metadata={
                        "derivation": question.get("derivation", ""),
                        "req_comparison": question.get("req_comparison", False),
                        "answer_from": question.get("answer_from"),
                        "order": question.get("order"),
                    },
                )
            )
    return items


def load_tat_dqa(path: str | Path) -> list[EvaluationItem]:
    source = Path(path).resolve()
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, list):
        raise ValueError("TAT-DQA annotation root must be a JSON array")
    if not payload:
        return []
    if not isinstance(payload[0], dict):
        raise ValueError("TAT-DQA entries must be JSON objects")
    if "question_id" in payload[0]:
        return _load_flat(payload)
    if "doc" in payload[0] and "questions" in payload[0]:
        return _load_official(payload)
    raise ValueError("unrecognized TAT-DQA format")


def _component_keys(items: list[EvaluationItem]) -> dict[str, str]:
    """Group questions connected by shared documents to prevent split leakage."""
    parent: dict[str, str] = {}

    def find(value: str) -> str:
        parent.setdefault(value, value)
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: str, right: str) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    for item in items:
        docs = item.document_ids or [f"question:{item.question_id}"]
        for doc in docs:
            find(doc)
        for doc in docs[1:]:
            union(docs[0], doc)
    return {
        item.question_id: find((item.document_ids or [f"question:{item.question_id}"])[0])
        for item in items
    }


def build_manifest(
    source_path: str | Path,
    *,
    name: str,
    seed: int = 2026,
    selection_fraction: float = 1.0,
    max_items: int | None = None,
    split: str = "held_out",
) -> DatasetManifest:
    source = Path(source_path).resolve()
    items = load_tat_dqa(source)
    components = _component_keys(items)

    def selected(item: EvaluationItem) -> bool:
        value = hashlib.sha256(
            f"{seed}:{components[item.question_id]}".encode("utf-8")
        ).digest()
        ratio = int.from_bytes(value[:8], "big") / float(2**64)
        return ratio < selection_fraction

    chosen = [item for item in items if selected(item)]
    chosen.sort(key=lambda item: item.question_id)
    if max_items is not None:
        chosen = chosen[:max_items]
    if not chosen:
        raise ValueError("manifest selection produced no questions")
    source_hash = sha256_file(source)
    identity = json.dumps(
        {
            "source_sha256": source_hash,
            "seed": seed,
            "selection_fraction": selection_fraction,
            "split": split,
            "question_ids": [item.question_id for item in chosen],
        },
        sort_keys=True,
    )
    manifest_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    try:
        recorded_source = source.relative_to(ROOT_DIR).as_posix()
    except ValueError:
        recorded_source = str(source)
    return DatasetManifest(
        manifest_id=manifest_id,
        name=name,
        source_path=recorded_source,
        source_sha256=source_hash,
        seed=seed,
        selection_fraction=selection_fraction,
        split=split,
        items=chosen,
    )


def write_manifest(manifest: DatasetManifest, path: str | Path) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def read_manifest(path: str | Path) -> DatasetManifest:
    payload = json.loads(Path(path).resolve().read_text(encoding="utf-8"))
    return DatasetManifest.model_validate(payload)
