"""Small compatibility boundary around the Langfuse Python SDK.

The evaluator remains locally testable without credentials. A compliant final
run should set LANGFUSE_REQUIRED=true and configure the standard Langfuse keys.
"""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from app.models import DatasetManifest


class LangfuseBridge:
    def __init__(self) -> None:
        self.configured = bool(
            os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
        ) and os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() != "false"
        self.client: Any = None
        self.error: str | None = None
        if self.configured:
            try:
                from langfuse import get_client

                self.client = get_client()
                if not self.client.auth_check():
                    raise RuntimeError("Langfuse authentication failed")
            except Exception as exc:  # configuration/network errors belong in health
                self.error = str(exc)
                self.client = None

    @property
    def ready(self) -> bool:
        return self.client is not None and self.error is None

    def health(self) -> dict[str, Any]:
        return {"configured": self.configured, "ready": self.ready, "error": self.error}

    def trace_id(self, seed: str) -> str:
        if self.ready:
            return str(self.client.create_trace_id(seed=seed))
        import hashlib

        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]

    @contextmanager
    def question_trace(
        self,
        *,
        trace_id: str,
        question: str,
        metadata: dict[str, str],
    ) -> Iterator[Any]:
        if not self.ready:
            yield None
            return
        with self.client.start_as_current_observation(
            as_type="span",
            name="evaluation.question",
            input={"question": question},
            metadata=metadata,
            trace_context={"trace_id": trace_id},
        ) as observation:
            yield observation

    def import_dataset(self, manifest: DatasetManifest) -> dict[str, Any]:
        if not self.ready:
            return {"uploaded": False, "reason": self.error or "Langfuse is not configured"}
        self.client.create_dataset(
            name=manifest.name,
            description=f"LEDGER {manifest.split}; manifest {manifest.manifest_id}",
            metadata={
                "manifest_id": manifest.manifest_id,
                "source_sha256": manifest.source_sha256,
            },
        )
        for item in manifest.items:
            self.client.create_dataset_item(
                dataset_name=manifest.name,
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{manifest.name}:{item.question_id}")),
                input={"question": item.question, "document_ids": item.document_ids},
                expected_output={"answer": item.gold_answer, "scale": item.scale},
                metadata={
                    "answer_type": item.answer_type,
                    "is_answerable": item.is_answerable,
                    "document_ids": item.document_ids,
                    "question_id": item.question_id,
                    "gold_evidence": [
                        evidence.model_dump(mode="json") for evidence in item.gold_evidence
                    ],
                    "manifest_id": manifest.manifest_id,
                },
            )
        self.client.flush()
        return {"uploaded": True, "dataset_name": manifest.name, "items": len(manifest.items)}

    def score_trace(self, trace_id: str, metrics: dict[str, Any]) -> None:
        if not self.ready:
            return
        for name, value in metrics.items():
            if value is None:
                continue
            self.client.create_score(
                trace_id=trace_id,
                name=name,
                value=float(value),
                data_type="NUMERIC",
            )

    def flush(self) -> None:
        if self.ready:
            self.client.flush()
