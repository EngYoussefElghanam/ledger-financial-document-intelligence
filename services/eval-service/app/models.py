"""Strict internal contracts for datasets and evaluation runs."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


Scale = Literal["", "thousand", "million", "billion", "percent"]
RunVariant = Literal["reranker_on", "reranker_off"]
RunState = Literal[
    "queued", "running", "completed", "completed_with_errors", "failed"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GoldEvidence(StrictModel):
    document_id: str
    source_document: str | None = None
    page: int | None = None
    content_type: str | None = None
    facts: list[str] = Field(default_factory=list)
    block_ids: list[str] = Field(default_factory=list)


class EvaluationItem(StrictModel):
    question_id: str
    question: str
    gold_answer: Any = None
    answer_type: str
    scale: Scale = ""
    is_answerable: bool = True
    document_ids: list[str] = Field(default_factory=list)
    gold_evidence: list[GoldEvidence] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetManifest(StrictModel):
    manifest_id: str
    name: str
    source_path: str
    source_sha256: str
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    seed: int = 2026
    selection_fraction: float = 1.0
    split: str = "held_out"
    items: list[EvaluationItem]


class DatasetImportRequest(StrictModel):
    name: str = "tat-dqa-held-out"
    source_path: str | None = None
    seed: int = 2026
    selection_fraction: float = Field(default=1.0, gt=0, le=1)
    max_items: int | None = Field(default=None, ge=1)
    split: str = "held_out"
    upload_to_langfuse: bool = True


class RunRequest(StrictModel):
    manifest_path: str | None = None
    run_name: str | None = None
    variant: RunVariant = "reranker_on"
    k_values: list[int] = Field(default_factory=lambda: [1, 3, 5, 10], min_length=1)
    concurrency: int = Field(default=1, ge=1, le=20)
    max_items: int | None = Field(default=None, ge=1)
    oracle_document_scope: bool = False
    orchestrator_url: HttpUrl | None = None
    timeout_seconds: float = Field(default=120.0, gt=0, le=900)
    absolute_tolerance: float = Field(default=1e-4, ge=0)
    relative_tolerance: float = Field(default=1e-3, ge=0)
    require_langfuse: bool = False


class RunSummary(StrictModel):
    run_id: str
    status: RunState
    run_name: str
    manifest_id: str
    variant: RunVariant
    attempted: int = 0
    completed: int = 0
    failed: int = 0
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    config_hash: str
    artifact_dir: str
    error: str | None = None
    langfuse_dataset: str | None = None
    langfuse_run_url: str | None = None
