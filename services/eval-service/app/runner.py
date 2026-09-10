"""Asynchronous, resumable end-to-end benchmark runner."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.answer_adapter import answer_to_prediction
from app.dataset import read_manifest
from app.langfuse_client import LangfuseBridge
from app.metrics import aggregate_results, score_answer, score_retrieval
from app.models import EvaluationItem, RunRequest, RunSummary
from app.storage import RunStorage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_hash(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


class EvaluationRunner:
    def __init__(self, storage: RunStorage, langfuse: LangfuseBridge):
        self.storage = storage
        self.langfuse = langfuse
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def create(self, request: RunRequest, default_manifest_path: Path,
               corpus: dict[str, Any] | None = None) -> RunSummary:
        manifest_path = Path(request.manifest_path or default_manifest_path).resolve()
        manifest = read_manifest(manifest_path)
        config = request.model_dump(mode="json")
        config["evaluator_version"] = "1.1.0"
        config["manifest_path"] = str(manifest_path)
        config["manifest_id"] = manifest.manifest_id
        if corpus is not None:
            indexed = sorted(
                ({key: row.get(key) for key in ("document_id", "sha256", "total_chunks", "indexed_at")}
                 for row in corpus.get("documents", []) if row.get("status") == "indexed"),
                key=lambda row: row["document_id"],
            )
            config["corpus_fingerprint"] = _config_hash({"documents": indexed})
            config["indexed_document_count"] = len(indexed)
        config_hash = _config_hash(config)
        run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
        summary = RunSummary(
            run_id=run_id,
            status="queued",
            run_name=request.run_name or f"{manifest.name}-{request.variant}",
            manifest_id=manifest.manifest_id,
            variant=request.variant,
            created_at=_now(),
            config_hash=config_hash,
            artifact_dir=str((self.storage.run_dir / run_id).resolve()),
            langfuse_dataset=manifest.name if self.langfuse.ready else None,
        )
        self.storage.create_run(summary, config)
        if corpus is not None:
            self.storage.write_artifact(run_id, "corpus.json", {
                "captured_at": _now(), "fingerprint": config["corpus_fingerprint"],
                "documents": indexed,
            })
        self.tasks[run_id] = asyncio.create_task(
            self._execute(summary, request, manifest_path)
        )
        return summary

    def resume(self, run_id: str) -> RunSummary:
        active = self.tasks.get(run_id)
        if active is not None and not active.done():
            raise ValueError("run is already active")
        summary = self.storage.read_status(run_id)
        if summary.status in {"completed", "completed_with_errors"}:
            raise ValueError("completed runs are immutable and cannot be resumed")
        config = self.storage.read_config(run_id)
        allowed = set(RunRequest.model_fields)
        request = RunRequest.model_validate(
            {key: value for key, value in config.items() if key in allowed}
        )
        manifest_path = Path(config["manifest_path"]).resolve()
        summary.status = "queued"
        summary.error = None
        summary.finished_at = None
        self.storage.write_status(summary)
        self.tasks[run_id] = asyncio.create_task(
            self._execute(summary, request, manifest_path)
        )
        return summary

    async def _execute(
        self, summary: RunSummary, request: RunRequest, manifest_path: Path
    ) -> None:
        manifest = read_manifest(manifest_path)
        all_items = manifest.items[: request.max_items] if request.max_items else manifest.items
        existing_rows = self.storage.read_items(summary.run_id)
        completed_ids = {row["question_id"] for row in existing_rows}
        items = [item for item in all_items if item.question_id not in completed_ids]
        summary.status = "running"
        summary.started_at = _now()
        summary.attempted = len(all_items)
        summary.completed = len(existing_rows)
        summary.failed = sum(
            (row.get("system") or {}).get("status") not in {"ok", "refusal"}
            for row in existing_rows
        )
        self.storage.write_status(summary)
        semaphore = asyncio.Semaphore(request.concurrency)
        status_lock = asyncio.Lock()

        async def one(item: EvaluationItem) -> None:
            async with semaphore:
                row = await self._evaluate_item(summary, request, item)
                self.storage.append_item(summary.run_id, row)
                async with status_lock:
                    summary.completed += 1
                    if (row.get("system") or {}).get("status") not in {"ok", "refusal"}:
                        summary.failed += 1
                    self.storage.write_status(summary)

        try:
            await asyncio.gather(*(one(item) for item in items))
            rows = self.storage.read_items(summary.run_id)
            metrics = aggregate_results(rows)
            predictions = {
                row["question_id"]: [
                    row["prediction"]["answer"], row["prediction"]["scale"]
                ]
                for row in rows
            }
            failures = [
                row
                for row in rows
                if (row.get("answer_metrics") or {}).get("em") != 1.0
                or (row.get("system") or {}).get("status") not in {"ok", "refusal"}
            ]
            self.storage.write_artifact(summary.run_id, "metrics.json", metrics)
            self.storage.write_artifact(summary.run_id, "predictions.json", predictions)
            self.storage.write_artifact(summary.run_id, "failures.json", failures)
            self.storage.write_artifact(
                summary.run_id,
                "manifest.json",
                manifest.model_dump(mode="json", exclude={"items"}),
            )
            self.storage.write_artifact(
                summary.run_id,
                "langfuse.json",
                {
                    "configured": self.langfuse.configured,
                    "ready": self.langfuse.ready,
                    "dataset": manifest.name if self.langfuse.ready else None,
                    "run_url": summary.langfuse_run_url,
                    "error": self.langfuse.error,
                },
            )
            self.storage.write_text_artifact(
                summary.run_id,
                "summary.md",
                self._summary_markdown(summary, metrics),
            )
            summary.status = "completed_with_errors" if summary.failed else "completed"
        except Exception as exc:
            summary.status = "failed"
            summary.error = str(exc)
        finally:
            summary.finished_at = _now()
            self.storage.write_status(summary)
            self.langfuse.flush()

    @staticmethod
    def _summary_markdown(summary: RunSummary, metrics: dict[str, Any]) -> str:
        answer = metrics.get("answer") or {}
        retrieval = metrics.get("retrieval") or {}
        system = metrics.get("system") or {}
        latency = system.get("latency_ms") or {}
        lines = [
            f"# Evaluation run {summary.run_id}\n\n"
            f"- Variant: `{summary.variant}`\n"
            f"- Manifest: `{summary.manifest_id}`\n"
            f"- Attempted: {metrics.get('attempted', 0)}\n"
            f"- Exact Match: {answer.get('exact_match')}\n"
            f"- F1: {answer.get('f1')}\n"
            f"- Numerical accuracy: {answer.get('numerical_accuracy')} "
            f"(n={answer.get('numerical_count', 0)})\n"
            f"- Mean latency (ms): {latency.get('mean')}\n"
            f"- P95 latency (ms): {latency.get('p95')}\n"
            f"- Average LLM calls: {system.get('average_llm_calls')}\n"
            f"- Average total tokens: {system.get('average_total_tokens')}\n"
            f"- Total approximate cost (USD): {system.get('total_cost_usd')}\n"
            f"- Status counts: `{json.dumps(system.get('statuses', {}), sort_keys=True)}`\n"
            f"- Final retrieval mapping coverage: {retrieval.get('mapping_coverage')}\n"
            f"- Candidate retrieval mapping coverage: "
            f"{retrieval.get('candidate_mapping_coverage')}\n"
        ]
        for label, key in (
            ("Final reranked retrieval", "metrics_by_k"),
            ("Pre-rerank candidate retrieval", "candidate_metrics_by_k"),
        ):
            values = retrieval.get(key) or {}
            if values:
                lines.append(f"\n## {label}\n\n")
                lines.append("| K | Recall | Precision | Hit Rate | MRR |\n")
                lines.append("|---:|---:|---:|---:|---:|\n")
                for k, detail in sorted(values.items(), key=lambda pair: int(pair[0])):
                    lines.append(
                        f"| {k} | {detail.get('recall')} | {detail.get('precision')} | "
                        f"{detail.get('hit_rate')} | {detail.get('mrr')} |\n"
                    )
        return "".join(lines)

    async def _evaluate_item(
        self, summary: RunSummary, request: RunRequest, item: EvaluationItem
    ) -> dict[str, Any]:
        request_id = f"{summary.run_id}:{item.question_id}"
        trace_id = self.langfuse.trace_id(request_id)
        orchestrator_url = str(request.orchestrator_url or "http://localhost:8006").rstrip("/")
        document_id = item.document_ids[0] if request.oracle_document_scope and item.document_ids else None
        status = "ok"
        error: str | None = None
        raw_answer: dict[str, Any] | None = None
        diagnostics: dict[str, Any] = {}
        started = time.perf_counter()
        metadata = {
            "run_id": summary.run_id,
            "question_id": item.question_id,
            "variant": request.variant,
            "config_hash": summary.config_hash,
        }
        with self.langfuse.question_trace(
            trace_id=trace_id, question=item.question, metadata=metadata
        ) as observation:
            try:
                async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                    response = await client.post(
                        f"{orchestrator_url}/ask",
                        json={
                            "question": item.question,
                            "document_id": document_id,
                            "include_diagnostics": True,
                            "evaluation_variant": request.variant,
                            "request_id": request_id,
                            "trace_id": trace_id,
                            "parent_span_id": (
                                getattr(observation, "id", None) if observation is not None else None
                            ),
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                if isinstance(payload, dict) and isinstance(payload.get("answer"), dict):
                    raw_answer = payload["answer"]
                    diagnostics = payload.get("diagnostics") or {}
                elif isinstance(payload, dict):
                    raw_answer = payload
                else:
                    raise ValueError("orchestrator returned a non-object response")
                if raw_answer.get("answer_type") == "insufficient_evidence":
                    status = "refusal"
            except httpx.TimeoutException as exc:
                status, error = "timeout", str(exc)
            except httpx.HTTPStatusError as exc:
                status = "dependency_error" if exc.response.status_code >= 500 else "invalid_answer"
                error = f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"
            except httpx.RequestError as exc:
                status, error = "dependency_error", str(exc)
            except Exception as exc:
                status, error = "invalid_answer", str(exc)

            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            predicted_answer, predicted_scale = answer_to_prediction(raw_answer)
            answer_metrics = score_answer(
                gold_answer=item.gold_answer,
                gold_scale=item.scale,
                gold_answer_type=item.answer_type,
                is_answerable=item.is_answerable,
                predicted_answer=predicted_answer,
                predicted_scale=predicted_scale,
                absolute_tolerance=request.absolute_tolerance,
                relative_tolerance=request.relative_tolerance,
            )
            agent_diagnostics = diagnostics.get("agent") or diagnostics
            if status not in {"ok", "refusal"}:
                answer_metrics["em"] = 0.0
                answer_metrics["f1"] = 0.0
            retrieval_steps = agent_diagnostics.get("retrieval_steps") or []
            returned = retrieval_steps[-1].get("results", []) if retrieval_steps else []
            candidates = retrieval_steps[-1].get("candidates", []) if retrieval_steps else []
            retrieval_metrics = score_retrieval(item.gold_evidence, returned, request.k_values)
            candidate_metrics = score_retrieval(
                item.gold_evidence, candidates, request.k_values
            )
            if not retrieval_steps:
                retrieval_metrics = score_retrieval([], [], request.k_values)
                candidate_metrics = score_retrieval([], [], request.k_values)
            usage = agent_diagnostics.get("usage") or {}
            row = {
                "run_id": summary.run_id,
                "question_id": item.question_id,
                "document_id": document_id,
                "question": item.question,
                "gold": {
                    "answer": item.gold_answer,
                    "answer_type": item.answer_type,
                    "scale": item.scale,
                    "is_answerable": item.is_answerable,
                    "document_ids": item.document_ids,
                    "document_count": len(set(item.document_ids)),
                    "page_count": len(
                        {
                            (evidence.document_id, evidence.page)
                            for evidence in item.gold_evidence
                            if evidence.page is not None
                        }
                    ),
                    "evidence_source": item.metadata.get("answer_from")
                    or "+".join(
                        sorted(
                            {
                                evidence.content_type
                                for evidence in item.gold_evidence
                                if evidence.content_type
                            }
                        )
                    )
                    or "unknown",
                },
                "prediction": {
                    "raw": raw_answer,
                    "answer": predicted_answer,
                    "scale": predicted_scale,
                },
                "answer_metrics": answer_metrics,
                "retrieval": {
                    **retrieval_metrics,
                    "candidate_metrics": candidate_metrics,
                    "candidate_ids": (
                        retrieval_steps[-1].get("candidate_ids", []) if retrieval_steps else []
                    ),
                    "reranked_ids": [
                        result.get("chunk_id") for result in returned if result.get("chunk_id")
                    ],
                },
                "system": {
                    "status": status,
                    "latency_ms": latency_ms,
                    "llm_calls": usage.get("llm_calls"),
                    "input_tokens": usage.get("input_tokens"),
                    "output_tokens": usage.get("output_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "cost_usd": usage.get("cost_usd"),
                    "retries": agent_diagnostics.get("retries"),
                    "configuration": agent_diagnostics.get("configuration"),
                    "error": error,
                },
                "trace_id": trace_id,
                "config_hash": summary.config_hash,
                "metadata": item.metadata,
            }
            if observation is not None:
                observation.update(output={"prediction": row["prediction"], "status": status})
            trace_scores = dict(answer_metrics)
            trace_scores["retrieval_mapping_coverage"] = retrieval_metrics.get(
                "mapping_coverage"
            )
            trace_scores["candidate_retrieval_mapping_coverage"] = candidate_metrics.get(
                "mapping_coverage"
            )
            for prefix, detail in (
                ("retrieval", retrieval_metrics),
                ("candidate_retrieval", candidate_metrics),
            ):
                for k, values in detail.get("metrics_by_k", {}).items():
                    for name, value in values.items():
                        trace_scores[f"{prefix}_{name}@{k}"] = value
            trace_scores.update(
                {
                    "latency_ms": latency_ms,
                    "llm_calls": usage.get("llm_calls"),
                    "total_tokens": usage.get("total_tokens"),
                    "cost_usd": usage.get("cost_usd"),
                }
            )
            self.langfuse.score_trace(trace_id, trace_scores)
            return row
