"""Convert LEDGER's typed answer into TAT-DQA's answer/scale pair."""

from __future__ import annotations

import re
from typing import Any


SCALES = ("thousand", "million", "billion", "percent")


def _explicit_scale(value: Any) -> str:
    text = str(value).lower()
    if "%" in text or re.search(r"\bper\s*cent\b", text):
        return "percent"
    for scale in SCALES[:-1]:
        if re.search(rf"\b{scale}s?\b", text):
            return scale
    return ""


def answer_to_prediction(answer: dict[str, Any] | None) -> tuple[Any, str]:
    if not isinstance(answer, dict):
        return None, ""
    answer_type = answer.get("answer_type")
    params = answer.get("params") if isinstance(answer.get("params"), dict) else {}
    if answer_type == "insufficient_evidence":
        return None, ""
    if answer_type == "multi_span":
        value = params.get("values")
    else:
        value = params.get("value")
    scale = str(params.get("scale") or "").lower()
    if scale not in {"", *SCALES}:
        scale = ""
    if not scale:
        candidates = value if isinstance(value, list) else [value]
        inferred = {_explicit_scale(candidate) for candidate in candidates}
        inferred.discard("")
        if len(inferred) == 1:
            scale = inferred.pop()
    return value, scale

