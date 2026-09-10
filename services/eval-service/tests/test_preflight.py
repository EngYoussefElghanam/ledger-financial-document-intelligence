"""Preflight must fail before creating a run when the system cannot answer."""
import os
os.environ["LANGFUSE_TRACING_ENABLED"] = "false"

import httpx
import pytest
from fastapi import HTTPException
import app.main as api
from app.models import RunRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("ready, expected", [(False, 503), (True, 409)])
async def test_run_rejected_before_allocation(monkeypatch, ready, expected):
    real_client = httpx.AsyncClient

    def respond(request):
        if request.url.path == "/ready":
            return httpx.Response(200, json={"ready": ready})
        return httpx.Response(200, json={"documents": []})

    monkeypatch.setattr(api.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(api, "LANGFUSE_REQUIRED", False)
    def forbidden(*args):
        pytest.fail("Run allocated before prerequisites passed")
    monkeypatch.setattr(api.runner, "create", forbidden)
    with pytest.raises(HTTPException) as caught:
        await api.create_run(RunRequest(
            manifest_path="data/evaluation/manifests/2d95de53424cc9c5.json",
            max_items=1,
        ))
    assert caught.value.status_code == expected
