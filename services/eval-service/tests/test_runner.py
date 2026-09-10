from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

import app.runner as runner_module
from app.models import EvaluationItem, GoldEvidence, RunRequest, RunSummary
from app.runner import EvaluationRunner
from app.storage import RunStorage


class FakeLangfuse:
    configured = False
    ready = False
    error = None

    def trace_id(self, seed):
        return "a" * 32

    @contextmanager
    def question_trace(self, **kwargs):
        yield None

    def score_trace(self, *args, **kwargs):
        return None

    def flush(self):
        return None


@pytest.mark.anyio
async def test_corpus_snapshot_is_saved_and_order_independent(tmp_path, monkeypatch):
    runner = EvaluationRunner(RunStorage(tmp_path), FakeLangfuse())

    async def no_execution(*args):
        pass

    monkeypatch.setattr(runner, "_execute", no_execution)
    manifest = Path(__file__).resolve().parents[3] / "data/evaluation/manifests/2d95de53424cc9c5.json"
    records = [
        {"document_id": "b", "sha256": "bbb", "total_chunks": 2, "status": "indexed"},
        {"document_id": "a", "sha256": "aaa", "total_chunks": 1, "status": "indexed"},
        {"document_id": "c", "status": "failed"},
    ]
    first = runner.create(RunRequest(), manifest, corpus={"documents": records})
    second = runner.create(RunRequest(), manifest, corpus={"documents": list(reversed(records))})
    await runner.tasks[first.run_id]
    await runner.tasks[second.run_id]
    config = runner.storage.read_config(first.run_id)
    assert config["indexed_document_count"] == 2
    assert config["corpus_fingerprint"] == runner.storage.read_config(second.run_id)["corpus_fingerprint"]
    assert (runner.storage.run_dir / first.run_id / "corpus.json").exists()


class FakeResponse:
    status_code = 200
    text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "answer": {
                "answer_type": "direct",
                "evidence": [{"document_id": "doc-1", "page": 1}],
                "params": {"value": "42", "scale": "million"},
            },
            "diagnostics": {
                "agent": {
                    "retries": 0,
                    "usage": {
                        "llm_calls": 2,
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                        "cost_usd": 0.001,
                    },
                    "retrieval_steps": [
                        {
                            "candidate_ids": ["chunk-1"],
                            "candidates": [
                                {
                                    "chunk_id": "candidate-1",
                                    "document_id": "doc-1",
                                    "page_number": 1,
                                }
                            ],
                            "results": [
                                {
                                    "chunk_id": "chunk-1",
                                    "metadata": {
                                        "document_id": "doc-1",
                                        "page_number": 1,
                                    },
                                }
                            ],
                        }
                    ],
                }
            },
        }


class FakeAsyncClient:
    last_payload = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json):
        self.__class__.last_payload = json
        return FakeResponse()


@pytest.fixture
def storage_path():
    path = Path(__file__).parent / f"storage-{uuid4().hex}"
    yield path
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    if path.exists():
        path.rmdir()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_runner_calls_real_contract_shape_and_scores_diagnostics(monkeypatch, storage_path):
    monkeypatch.setattr(runner_module.httpx, "AsyncClient", FakeAsyncClient)
    runner = EvaluationRunner(RunStorage(storage_path), FakeLangfuse())
    summary = RunSummary(
        run_id="run-1",
        status="running",
        run_name="test",
        manifest_id="manifest",
        variant="reranker_off",
        created_at="2026-01-01T00:00:00Z",
        config_hash="config",
        artifact_dir=str(storage_path),
    )
    item = EvaluationItem(
        question_id="q1",
        question="What was revenue?",
        gold_answer="42",
        answer_type="span",
        scale="million",
        document_ids=["doc-1"],
        gold_evidence=[GoldEvidence(document_id="doc-1", page=1)],
    )
    row = await runner._evaluate_item(summary, RunRequest(variant="reranker_off"), item)
    assert FakeAsyncClient.last_payload["include_diagnostics"] is True
    assert FakeAsyncClient.last_payload["document_id"] is None
    assert FakeAsyncClient.last_payload["evaluation_variant"] == "reranker_off"
    assert row["answer_metrics"]["em"] == 1
    assert row["retrieval"]["metrics_by_k"]["1"]["hit_rate"] == 1
    assert row["retrieval"]["candidate_metrics"]["metrics_by_k"]["1"]["hit_rate"] == 1
    assert row["system"]["llm_calls"] == 2
    assert row["system"]["cost_usd"] == 0.001


@pytest.mark.anyio
async def test_dependency_failure_is_not_correct_abstention(monkeypatch, storage_path):
    class BrokenClient(FakeAsyncClient):
        async def post(self, url, json):
            raise httpx.ConnectError("agent unavailable")

    monkeypatch.setattr(runner_module.httpx, "AsyncClient", BrokenClient)
    runner = EvaluationRunner(RunStorage(storage_path), FakeLangfuse())
    summary = RunSummary(run_id="failed", status="running", run_name="test",
                         manifest_id="test", variant="reranker_on",
                         created_at="2026-01-01T00:00:00Z", config_hash="test",
                         artifact_dir=str(storage_path))
    item = EvaluationItem(question_id="q", question="Unknown?", gold_answer=None,
                          answer_type="unanswerable", is_answerable=False)
    row = await runner._evaluate_item(summary, RunRequest(), item)
    assert row["system"]["status"] == "dependency_error"
    assert row["answer_metrics"]["em"] == 0
    assert row["answer_metrics"]["f1"] == 0
    assert row["retrieval"]["mapping_coverage"] == 0
