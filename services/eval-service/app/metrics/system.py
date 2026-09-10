"""Aggregate answer, retrieval, and runtime metrics without dropping failures."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from statistics import mean, median
from typing import Any


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _average(values: list[float]) -> float | None:
    return mean(values) if values else None


def _answer_rollup(details: list[dict[str, Any]]) -> dict[str, Any]:
    em_values = [float(item.get("em", 0.0)) for item in details]
    f1_values = [float(item.get("f1", 0.0)) for item in details]
    numeric_values = [
        float(value)
        for item in details
        if (value := item.get("numerical_accuracy")) is not None
    ]
    return {
        "exact_match": _average(em_values),
        "exact_match_numerator": sum(em_values),
        "exact_match_denominator": len(em_values),
        "f1": _average(f1_values),
        "f1_sum": sum(f1_values),
        "f1_denominator": len(f1_values),
        "numerical_accuracy": _average(numeric_values),
        "numerical_numerator": sum(numeric_values),
        "numerical_count": len(numeric_values),
    }


def aggregate_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    answer_metrics = [row.get("answer_metrics") or {} for row in rows]
    latencies = [
        float(row["system"]["latency_ms"])
        for row in rows
        if (row.get("system") or {}).get("latency_ms") is not None
    ]
    statuses = Counter((row.get("system") or {}).get("status", "unknown") for row in rows)

    retrieval: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    candidate_retrieval: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    level_counts = Counter()
    candidate_level_counts = Counter()
    for row in rows:
        detail = row.get("retrieval") or {}
        level_counts[detail.get("mapping_level", "unavailable")] += 1
        for k, metrics in (detail.get("metrics_by_k") or {}).items():
            for name, value in metrics.items():
                retrieval[k][name].append(float(value))
        candidate_detail = detail.get("candidate_metrics") or {}
        candidate_level_counts[
            candidate_detail.get("mapping_level", "unavailable")
        ] += 1
        for k, metrics in (candidate_detail.get("metrics_by_k") or {}).items():
            for name, value in metrics.items():
                candidate_retrieval[k][name].append(float(value))

    slices: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row, detail in zip(rows, answer_metrics):
        gold = row.get("gold") or {}
        dimensions = {
            "answer_type": gold.get("answer_type", "unknown"),
            "evidence_source": gold.get("evidence_source", "unknown"),
            "document_count": str(gold.get("document_count", "unknown")),
            "page_count": str(gold.get("page_count", "unknown")),
            "system_status": (row.get("system") or {}).get("status", "unknown"),
        }
        for dimension, value in dimensions.items():
            slices[dimension][str(value)].append(detail)

    system_rows = [row.get("system") or {} for row in rows]
    token_fields = ("llm_calls", "input_tokens", "output_tokens", "total_tokens", "retries")
    system_averages = {
        f"average_{field}": _average(
            [float(item[field]) for item in system_rows if item.get(field) is not None]
        )
        for field in token_fields
    }
    costs = [float(item["cost_usd"]) for item in system_rows if item.get("cost_usd") is not None]
    configurations = Counter(
        json.dumps(item["configuration"], sort_keys=True)
        for item in system_rows
        if item.get("configuration")
    )
    return {
        "attempted": total,
        "evaluator_version": "1.1.0",
        "answer": {
            **_answer_rollup(answer_metrics),
            "slices": {
                dimension: {
                    value: _answer_rollup(details)
                    for value, details in dimension_values.items()
                }
                for dimension, dimension_values in slices.items()
            },
        },
        "retrieval": {
            "attempted": total,
            "scorable_count": total - level_counts.get("unavailable", 0),
            "mapping_coverage": (
                (total - level_counts.get("unavailable", 0)) / total if total else 0.0
            ),
            "mapping_levels": dict(level_counts),
            "metrics_by_k": {
                k: {name: _average(values) for name, values in metrics.items()}
                for k, metrics in retrieval.items()
            },
            "metric_counts_by_k": {
                k: {name: len(values) for name, values in metrics.items()}
                for k, metrics in retrieval.items()
            },
            "candidate_scorable_count": total
            - candidate_level_counts.get("unavailable", 0),
            "candidate_mapping_coverage": (
                (total - candidate_level_counts.get("unavailable", 0)) / total
                if total
                else 0.0
            ),
            "candidate_mapping_levels": dict(candidate_level_counts),
            "candidate_metrics_by_k": {
                k: {name: _average(values) for name, values in metrics.items()}
                for k, metrics in candidate_retrieval.items()
            },
            "candidate_metric_counts_by_k": {
                k: {name: len(values) for name, values in metrics.items()}
                for k, metrics in candidate_retrieval.items()
            },
        },
        "system": {
            "latency_ms": {
                "mean": _average(latencies),
                "median": median(latencies) if latencies else None,
                "p95": _percentile(latencies, 0.95),
                "min": min(latencies) if latencies else None,
                "max": max(latencies) if latencies else None,
                "count": len(latencies),
            },
            **system_averages,
            **{
                {
                    "llm_calls": "total_llm_calls",
                    "input_tokens": "total_input_tokens",
                    "output_tokens": "total_output_tokens",
                    "total_tokens": "total_tokens",
                    "retries": "total_retries",
                }[field]: sum(
                    float(item[field])
                    for item in system_rows
                    if item.get(field) is not None
                ) if any(item.get(field) is not None for item in system_rows) else None
                for field in token_fields
            },
            **{
                f"observed_{field}_count": sum(
                    item.get(field) is not None for item in system_rows
                )
                for field in token_fields
            },
            "average_cost_usd": _average(costs),
            "total_cost_usd": sum(costs) if costs else None,
            "cost_count": len(costs),
            "statuses": dict(statuses),
            "status_denominator": total,
            "observed_configurations": [
                {"configuration": json.loads(value), "query_count": count}
                for value, count in configurations.items()
            ],
            "rates": {
                status: count / total if total else 0.0 for status, count in statuses.items()
            },
        },
    }
