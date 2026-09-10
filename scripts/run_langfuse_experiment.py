"""Run the real LEDGER pipeline as a Langfuse dataset experiment."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv
from langfuse import get_client


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "services" / "eval-service"))
load_dotenv(ROOT_DIR / ".env", override=False)

from app.answer_adapter import answer_to_prediction  # noqa: E402
from app.metrics.answer import score_answer  # noqa: E402
from app.metrics.retrieval import score_retrieval  # noqa: E402
from app.models import GoldEvidence  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_name")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--orchestrator-url", default="http://localhost:8000")
    parser.add_argument("--variant", choices=["reranker_on", "reranker_off"], default="reranker_on")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()

    langfuse = get_client()
    if not langfuse.auth_check():
        raise SystemExit("Langfuse authentication failed")
    dataset = langfuse.get_dataset(args.dataset_name)

    def task(*, item, **kwargs):
        started = time.perf_counter()
        question = item.input["question"]
        payload = {
            "question": question,
            "document_id": None,
            "include_diagnostics": True,
            "evaluation_variant": args.variant,
            "request_id": f"{args.run_name}:{item.id}",
            "trace_id": langfuse.get_current_trace_id(),
            "parent_span_id": langfuse.get_current_observation_id(),
        }
        response = httpx.post(
            f"{args.orchestrator_url.rstrip('/')}/ask",
            json=payload,
            timeout=args.timeout,
        )
        response.raise_for_status()
        output = response.json()
        output["evaluation_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        return output

    def deterministic_scores(*, output, expected_output, metadata, **kwargs):
        answer = output.get("answer") if isinstance(output, dict) else None
        predicted_answer, predicted_scale = answer_to_prediction(answer)
        expected_output = expected_output or {}
        metadata = metadata or {}
        scores = score_answer(
            gold_answer=expected_output.get("answer"),
            gold_scale=expected_output.get("scale", ""),
            gold_answer_type=metadata.get("answer_type", "span"),
            is_answerable=metadata.get("is_answerable", True),
            predicted_answer=predicted_answer,
            predicted_scale=predicted_scale,
        )
        evaluations = [
            {"name": name, "value": value}
            for name, value in scores.items()
            if value is not None
        ]
        diagnostics = output.get("diagnostics") or {}
        agent = diagnostics.get("agent") or diagnostics
        retrieval_steps = agent.get("retrieval_steps") or []
        results = retrieval_steps[-1].get("results", []) if retrieval_steps else []
        candidates = retrieval_steps[-1].get("candidates", []) if retrieval_steps else []
        gold_evidence = [
            GoldEvidence.model_validate(value)
            for value in metadata.get("gold_evidence", [])
        ]
        retrieval = score_retrieval(gold_evidence, results, [1, 3, 5, 10])
        candidate_retrieval = score_retrieval(
            gold_evidence, candidates, [1, 3, 5, 10]
        )
        for k, values in retrieval.get("metrics_by_k", {}).items():
            for name, value in values.items():
                evaluations.append({"name": f"retrieval_{name}@{k}", "value": value})
        for k, values in candidate_retrieval.get("metrics_by_k", {}).items():
            for name, value in values.items():
                evaluations.append(
                    {"name": f"candidate_retrieval_{name}@{k}", "value": value}
                )
        usage = agent.get("usage") or {}
        system_scores = {
            "latency_ms": output.get("evaluation_latency_ms"),
            "llm_calls": usage.get("llm_calls"),
            "total_tokens": usage.get("total_tokens"),
            "cost_usd": usage.get("cost_usd"),
            "retrieval_mapping_coverage": retrieval.get("mapping_coverage"),
        }
        evaluations.extend(
            {"name": name, "value": value}
            for name, value in system_scores.items()
            if value is not None
        )
        return evaluations

    result = dataset.run_experiment(
        name=args.run_name,
        run_name=args.run_name,
        description="LEDGER held-out end-to-end TAT-DQA evaluation",
        task=task,
        evaluators=[deterministic_scores],
        max_concurrency=args.concurrency,
        metadata={"variant": args.variant, "system": "ledger"},
    )
    print(result.format(include_item_results=True))
    if result.dataset_run_url:
        print(f"dataset_run_url={result.dataset_run_url}")
    langfuse.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
