"""
tests/test_main.py

Tests the FastAPI layer end to end: upload a real PDF through /process,
confirm it's retrievable via /documents/{id}, and confirm /process_batch
handles a directory (including a deliberately broken file, to check the
partial-failure path actually works before we trust it on the real
2,758-document TAT-DQA corpus).

Uses a real sample PDF and a real docling run - these are slower than
pure unit tests, but for this service the actual PDF -> JSON conversion
is the thing worth verifying, not just that Python objects glue together.
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, PROCESSED_DIR

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLE_PDF = FIXTURES / "sample1.pdf"

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_processed_dir():
    """Each test gets a clean data/processed/ so results from one test
    don't leak into another and hide a real bug."""
    if PROCESSED_DIR.exists():
        shutil.rmtree(PROCESSED_DIR)
    PROCESSED_DIR.mkdir(parents=True)
    yield


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_process_single_pdf():
    with SAMPLE_PDF.open("rb") as f:
        resp = client.post(
            "/process",
            params={"document_id": "torm_sample1"},
            files={"file": ("sample1.pdf", f, "application/pdf")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["document_id"] == "torm_sample1"
    assert body["page_count"] == 1

    page = body["pages"][0]
    assert len(page["tables"]) == 3
    # section attribution should point at the real heading, not a
    # table-internal row label like "EARNINGS PER SHARE"
    eps_table = page["tables"][1]
    assert "NOTE 26" in eps_table["section"]

    # confirm it was actually persisted, not just returned in-memory
    persisted_path = PROCESSED_DIR / "torm_sample1.json"
    assert persisted_path.exists()


def test_get_document_after_processing():
    with SAMPLE_PDF.open("rb") as f:
        client.post(
            "/process",
            params={"document_id": "torm_sample1"},
            files={"file": ("sample1.pdf", f, "application/pdf")},
        )

    resp = client.get("/documents/torm_sample1")
    assert resp.status_code == 200
    assert resp.json()["document_id"] == "torm_sample1"


def test_get_document_not_found():
    resp = client.get("/documents/does_not_exist")
    assert resp.status_code == 404


def test_reject_non_pdf():
    resp = client.post(
        "/process",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
    )
    assert resp.status_code == 400


def test_process_batch_handles_partial_failure(tmp_path):
    # one real PDF + one deliberately broken "PDF" in the same directory
    shutil.copy(SAMPLE_PDF, tmp_path / "good.pdf")
    (tmp_path / "broken.pdf").write_bytes(b"not a real pdf")

    resp = client.post("/process_batch", params={"directory": str(tmp_path)})
    assert resp.status_code == 200
    body = resp.json()

    assert body["total"] == 2
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    assert len(body["failures"]) == 1
    assert body["failures"][0]["file"] == "broken.pdf"


def test_process_batch_invalid_directory():
    resp = client.post("/process_batch", params={"directory": "/nonexistent/path"})
    assert resp.status_code == 400