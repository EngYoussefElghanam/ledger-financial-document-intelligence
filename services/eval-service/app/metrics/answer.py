"""TAT-DQA-style answer normalization, EM/F1, and numerical accuracy."""

from __future__ import annotations

import math
import re
import string
from collections import Counter
from functools import lru_cache
from typing import Any


SCALE_MULTIPLIER = {
    "": 1.0,
    "thousand": 1_000.0,
    "million": 1_000_000.0,
    "billion": 1_000_000_000.0,
    "percent": 0.01,
}


def _values(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _parse_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    text = str(value).strip().lower().replace(",", "").replace("$", "")
    text = re.sub(r"\b(thousand|million|billion|percent|per\s*cent)\b", "", text)
    text = text.replace("%", "").strip()
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    try:
        number = float(text)
    except ValueError:
        return None
    number = -number if negative else number
    return number if math.isfinite(number) else None


def normalize_text(value: Any) -> str:
    text = str(value).lower().replace("–", "-").replace("—", "-")
    text = re.sub(r"\bper\s*cent\b", "percent", text)
    punctuation = string.punctuation.replace(".", "").replace("-", "")
    text = text.translate(str.maketrans({char: " " for char in punctuation}))
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return " ".join(text.split())


def _canonical(value: Any, scale: str) -> str:
    number = _parse_number(value)
    if number is not None:
        normalized = f"{number:.10f}".rstrip("0").rstrip(".")
    else:
        normalized = normalize_text(value)
    if number is not None and scale and scale not in normalized.split():
        normalized = f"{normalized} {scale}".strip()
    return normalized


def _span_f1(prediction: str, gold: str) -> float:
    pred_tokens, gold_tokens = prediction.split(), gold.split()
    if not pred_tokens or not gold_tokens:
        return float(pred_tokens == gold_tokens)
    overlap = sum((Counter(pred_tokens) & Counter(gold_tokens)).values())
    if not overlap:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def _aligned_f1(predicted: list[str], gold: list[str]) -> float:
    if not predicted or not gold:
        return float(predicted == gold)
    scores = [[_span_f1(p, g) for g in gold] for p in predicted]

    @lru_cache(maxsize=None)
    def best(pred_index: int, used_gold_mask: int) -> float:
        if pred_index == len(predicted):
            return 0.0
        result = best(pred_index + 1, used_gold_mask)
        for gold_index in range(len(gold)):
            if not used_gold_mask & (1 << gold_index):
                result = max(
                    result,
                    scores[pred_index][gold_index]
                    + best(pred_index + 1, used_gold_mask | (1 << gold_index)),
                )
        return result

    return best(0, 0) / max(len(predicted), len(gold))


def score_answer(
    *,
    gold_answer: Any,
    gold_scale: str,
    gold_answer_type: str,
    is_answerable: bool,
    predicted_answer: Any,
    predicted_scale: str,
    absolute_tolerance: float = 1e-4,
    relative_tolerance: float = 1e-3,
) -> dict[str, float | None]:
    if not is_answerable or gold_answer_type == "unanswerable":
        correct_refusal = predicted_answer is None
        return {
            "em": float(correct_refusal),
            "f1": float(correct_refusal),
            "numerical_accuracy": None,
        }

    gold = sorted(_canonical(value, gold_scale) for value in _values(gold_answer))
    predicted = sorted(
        _canonical(value, predicted_scale) for value in _values(predicted_answer)
    )
    em = float(predicted == gold and bool(gold))
    f1 = _aligned_f1(predicted, gold)

    numerical_accuracy: float | None = None
    if gold_answer_type in {"arithmetic", "count", "counting"}:
        gold_number = _parse_number(_values(gold_answer)[0] if _values(gold_answer) else None)
        pred_number = _parse_number(
            _values(predicted_answer)[0] if _values(predicted_answer) else None
        )
        if gold_number is None or pred_number is None:
            numerical_accuracy = 0.0
        else:
            gold_scaled = gold_number * SCALE_MULTIPLIER.get(gold_scale, 1.0)
            pred_scaled = pred_number * SCALE_MULTIPLIER.get(predicted_scale, 1.0)
            tolerance = max(
                absolute_tolerance, relative_tolerance * abs(gold_scaled)
            )
            numerical_accuracy = float(abs(pred_scaled - gold_scaled) <= tolerance)
    return {"em": em, "f1": f1, "numerical_accuracy": numerical_accuracy}
