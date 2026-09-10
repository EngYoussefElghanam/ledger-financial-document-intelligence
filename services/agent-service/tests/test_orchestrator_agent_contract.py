"""HTTP contract test: the real orchestrator client calls the real agent route."""

import importlib.util
import importlib
import sys
import types
from pathlib import Path

import httpx
import pytest

class StubGraph:
    def invoke(self, state):
        return {
            "answer": {
                "answer_type": "direct",
                "evidence": [{"document_id": state["document_id"], "page": 1}],
                "params": {"value": state["question"]},
            }
        }


graph_module = types.ModuleType("app.graph")
graph_module.graph = StubGraph()
sys.modules["app.graph"] = graph_module
agent_main = importlib.import_module("app.main")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_real_client_reaches_real_ask_route(monkeypatch):
    config = types.ModuleType("app.config")
    config.AGENT_SERVICE_URL = "http://agent-service"
    config.USE_MOCK_AGENT = False
    monkeypatch.setitem(sys.modules, "app.config", config)

    client_path = (
        Path(__file__).resolve().parents[2]
        / "orchestrator-api"
        / "app"
        / "agent_client.py"
    )
    spec = importlib.util.spec_from_file_location("real_agent_client", client_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    real_async_client = httpx.AsyncClient

    def asgi_client(**kwargs):
        kwargs["transport"] = httpx.ASGITransport(app=agent_main.app)
        return real_async_client(**kwargs)

    monkeypatch.setattr(module.httpx, "AsyncClient", asgi_client)
    answer = await module.ask_agent("question-through-http", "contract_doc")

    assert answer["params"]["value"] == "question-through-http"
    assert answer["evidence"][0]["document_id"] == "contract_doc"
