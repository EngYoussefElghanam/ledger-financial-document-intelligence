from app.metrics.system import aggregate_results


def row(status, latency, em, numeric=None, candidate_hit=None):
    candidate_metrics = (
        {
            "mapping_level": "page",
            "metrics_by_k": {
                "1": {"recall": candidate_hit, "precision": candidate_hit,
                      "hit_rate": candidate_hit, "mrr": candidate_hit}
            },
        }
        if candidate_hit is not None
        else {}
    )
    return {
        "answer_metrics": {"em": em, "f1": em, "numerical_accuracy": numeric},
        "retrieval": {
            "mapping_level": "unavailable",
            "metrics_by_k": {},
            "candidate_metrics": candidate_metrics,
        },
        "system": {
            "status": status,
            "latency_ms": latency,
            "llm_calls": 2,
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "cost_usd": None,
            "retries": 0,
        },
    }


def test_failures_remain_in_answer_and_status_denominators():
    metrics = aggregate_results([row("ok", 100, 1, 1), row("timeout", 300, 0, 0)])
    assert metrics["attempted"] == 2
    assert metrics["answer"]["exact_match"] == 0.5
    assert metrics["answer"]["exact_match_numerator"] == 1
    assert metrics["answer"]["exact_match_denominator"] == 2
    assert metrics["answer"]["numerical_accuracy"] == 0.5
    assert metrics["system"]["latency_ms"]["mean"] == 200
    assert metrics["system"]["total_tokens"] == 30
    assert metrics["system"]["observed_total_tokens_count"] == 2
    assert metrics["system"]["rates"]["timeout"] == 0.5
    assert metrics["system"]["total_cost_usd"] is None


def test_candidate_retrieval_is_aggregated_separately():
    metrics = aggregate_results(
        [row("ok", 100, 1, candidate_hit=1), row("ok", 100, 1, candidate_hit=0)]
    )
    assert metrics["retrieval"]["candidate_mapping_coverage"] == 1
    assert metrics["retrieval"]["candidate_metrics_by_k"]["1"]["hit_rate"] == 0.5
