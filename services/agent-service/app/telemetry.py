"""Request-local diagnostics used by the held-out evaluator."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.config import (
    AGENT_MODEL,
    AGENT_PROMPT_VERSION,
    AGENT_PROVIDER,
    LLM_INPUT_COST_PER_MILLION,
    LLM_OUTPUT_COST_PER_MILLION,
    LLM_PRICE_EFFECTIVE_DATE,
    LLM_PRICE_SOURCE,
)
from ledger_observability import observation


@dataclass
class RequestTelemetry:
    variant: str = "reranker_on"
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None
    retrieval_steps: list[dict[str, Any]] = field(default_factory=list)
    llm_stages: list[dict[str, Any]] = field(default_factory=list)


_current: ContextVar[RequestTelemetry | None] = ContextVar("ledger_telemetry", default=None)


@contextmanager
def telemetry_scope(
    variant: str,
    *,
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    question: str | None = None,
    request_id: str | None = None,
) -> Iterator[RequestTelemetry]:
    telemetry = RequestTelemetry(variant=variant)
    token = _current.set(telemetry)
    try:
        with observation(
            "agent.graph",
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            input={"question": question},
            metadata={"variant": variant, "request_id": request_id},
        ) as span:
            yield telemetry
            span.update(output={"usage": as_dict(telemetry)["usage"]})
    finally:
        _current.reset(token)


def current() -> RequestTelemetry | None:
    return _current.get()


def reranker_enabled() -> bool:
    telemetry = current()
    return telemetry is None or telemetry.variant != "reranker_off"


def record_llm(stage: str, response: Any) -> None:
    telemetry = current()
    if telemetry is None:
        return
    telemetry.llm_calls += 1
    usage = getattr(response, "usage_metadata", None) or {}
    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or response_metadata.get("usage") or {}
    input_tokens = usage.get("input_tokens", token_usage.get("prompt_tokens", 0)) or 0
    output_tokens = usage.get("output_tokens", token_usage.get("completion_tokens", 0)) or 0
    total_tokens = usage.get(
        "total_tokens", token_usage.get("total_tokens", input_tokens + output_tokens)
    ) or 0
    telemetry.input_tokens += int(input_tokens)
    telemetry.output_tokens += int(output_tokens)
    telemetry.total_tokens += int(total_tokens)
    call_cost = (
        float(input_tokens) * LLM_INPUT_COST_PER_MILLION
        + float(output_tokens) * LLM_OUTPUT_COST_PER_MILLION
    ) / 1_000_000
    if LLM_INPUT_COST_PER_MILLION or LLM_OUTPUT_COST_PER_MILLION:
        telemetry.cost_usd = (telemetry.cost_usd or 0.0) + call_cost
    telemetry.llm_stages.append(
        {
            "stage": stage,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "total_tokens": int(total_tokens),
            "model": response_metadata.get("model_name") or response_metadata.get("model"),
            "cost_usd": call_cost if (LLM_INPUT_COST_PER_MILLION or LLM_OUTPUT_COST_PER_MILLION) else None,
        }
    )


def record_retrieval(payload: dict[str, Any], response: dict[str, Any]) -> None:
    telemetry = current()
    if telemetry is None:
        return
    diagnostics = response.get("diagnostics") or {}
    telemetry.retrieval_steps.append(
        {
            "query": payload.get("query"),
            "limit": payload.get("limit"),
            "document_id": payload.get("document_id"),
            "content_type": payload.get("content_type"),
            "reranker_enabled": diagnostics.get("reranker_enabled", payload.get("rerank")),
            "candidate_ids": [
                candidate.get("chunk_id")
                for candidate in diagnostics.get("candidates", [])
                if candidate.get("chunk_id")
            ],
            "candidates": diagnostics.get("candidates", []),
            "results": response.get("results") or [],
        }
    )


def as_dict(telemetry: RequestTelemetry) -> dict[str, Any]:
    return {
        "variant": telemetry.variant,
        "configuration": {
            "provider": AGENT_PROVIDER,
            "model": AGENT_MODEL,
            "prompt_version": AGENT_PROMPT_VERSION,
            "cost_currency": "USD",
            "input_cost_per_million": LLM_INPUT_COST_PER_MILLION,
            "output_cost_per_million": LLM_OUTPUT_COST_PER_MILLION,
            "price_source": LLM_PRICE_SOURCE,
            "price_effective_date": LLM_PRICE_EFFECTIVE_DATE,
        },
        "usage": {
            "llm_calls": telemetry.llm_calls,
            "input_tokens": telemetry.input_tokens,
            "output_tokens": telemetry.output_tokens,
            "total_tokens": telemetry.total_tokens,
            "cost_usd": telemetry.cost_usd,
        },
        "retrieval_steps": telemetry.retrieval_steps,
        "llm_stages": telemetry.llm_stages,
    }
