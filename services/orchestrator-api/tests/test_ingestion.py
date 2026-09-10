import httpx
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.corpus_manifest as manifest_module
import app.main as main_module


PROCESSED_DOCUMENT = {
    "document_id": "dataset_001",
    "source_filename": "report.pdf",
    "page_count": 1,
    "pages": [
        {
            "page_number": 1,
            "blocks": [
                {
                    "block_id": "b1",
                    "content_type": "paragraph",
                    "text": "Revenue was 42 million.",
                    "section": "Revenue",
                    "bbox": [0, 0, 1, 1],
                }
            ],
            "tables": [],
        }
    ],
}


def _response(method, url, status, body):
    return httpx.Response(
        status,
        json=body,
        request=httpx.Request(method, url),
    )


class FakeServices:
    retrieval_fails = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, **kwargs):
        if url.endswith("/process"):
            document = {**PROCESSED_DOCUMENT, "document_id": kwargs["params"]["document_id"]}
            return _response("POST", url, 200, document)
        if url.endswith("/ingest") and self.retrieval_fails:
            return _response("POST", url, 503, {"detail": "not ready"})
        return _response("POST", url, 200, {"status": "success", "total_chunks": 1})

    async def get(self, url, **kwargs):
        document_id = url.rsplit("/", 1)[-1]
        return _response(
            "GET", url, 200, {**PROCESSED_DOCUMENT, "document_id": document_id}
        )


@pytest.fixture
def manifest_path():
    path = Path(__file__).parent / f"manifest-{uuid.uuid4().hex}.json"
    yield path
    path.unlink(missing_ok=True)


def test_failed_retrieval_is_persisted_and_resumable(monkeypatch, manifest_path):
    monkeypatch.setattr(manifest_module, "CORPUS_MANIFEST_PATH", manifest_path)
    services = FakeServices()
    monkeypatch.setattr(main_module.httpx, "AsyncClient", lambda: services)
    client = TestClient(main_module.app)

    failed = client.post(
        "/documents/ingest",
        params={"dataset_id": "dataset_001"},
        files={"file": ("report.pdf", b"%PDF test", "application/pdf")},
    )
    assert failed.status_code == 502
    ingestion_status = client.get("/ingestion").json()
    record = ingestion_status["documents"][0]
    assert record["status"] == "failed"
    assert record["processed_at"]
    assert record["failed_stage"] == "retrieval"
    assert ingestion_status["counts"] == {
        "uploaded": 1,
        "processed": 1,
        "indexed": 0,
        "failed": 1,
    }

    services.retrieval_fails = False
    resumed = client.post("/documents/dataset_001/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "indexed"

    documents = client.get("/documents").json()
    assert [document["document_id"] for document in documents] == ["dataset_001"]
    assert documents[0]["status"] == "indexed"


def test_stable_dataset_id_rejects_different_content(monkeypatch, manifest_path):
    monkeypatch.setattr(manifest_module, "CORPUS_MANIFEST_PATH", manifest_path)
    services = FakeServices()
    services.retrieval_fails = False
    monkeypatch.setattr(main_module.httpx, "AsyncClient", lambda: services)
    client = TestClient(main_module.app)

    first = client.post(
        "/documents/ingest",
        params={"dataset_id": "dataset_001"},
        files={"file": ("one.pdf", b"%PDF one", "application/pdf")},
    )
    second = client.post(
        "/documents/ingest",
        params={"dataset_id": "dataset_001"},
        files={"file": ("two.pdf", b"%PDF two", "application/pdf")},
    )

    assert first.status_code == 200
    assert second.status_code == 409
