"""One shared httpx.AsyncClient for the whole app's lifetime, created at
startup and reused across every downstream call to avoid rebuilding a
connection pool per request. See main.py's lifespan for setup/teardown."""

import httpx

_state: dict[str, httpx.AsyncClient | None] = {"client": None}


def set_client(client: httpx.AsyncClient) -> None:
    _state["client"] = client


def get_client() -> httpx.AsyncClient:
    if _state["client"] is None:
        raise RuntimeError("HTTP client not initialized - did the app startup run?")
    return _state["client"]