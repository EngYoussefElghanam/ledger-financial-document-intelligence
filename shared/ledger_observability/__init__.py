"""Optional Langfuse tracing shared by LEDGER services."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class SpanHandle:
    observation: Any = None

    @property
    def observation_id(self) -> str | None:
        return getattr(self.observation, "id", None)

    def update(self, **kwargs: Any) -> None:
        if self.observation is not None:
            self.observation.update(**kwargs)


def _client() -> Any:
    if os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
        return None
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        return None
    try:
        from langfuse import get_client

        return get_client()
    except Exception:
        return None


@contextmanager
def observation(
    name: str,
    *,
    as_type: str = "span",
    trace_id: str | None = None,
    parent_span_id: str | None = None,
    input: Any = None,
    metadata: dict[str, Any] | None = None,
    model: str | None = None,
) -> Iterator[SpanHandle]:
    client = _client()
    if client is None:
        yield SpanHandle()
        return
    kwargs: dict[str, Any] = {
        "as_type": as_type,
        "name": name,
        "input": input,
        "metadata": metadata,
    }
    if trace_id:
        trace_context = {"trace_id": trace_id}
        if parent_span_id:
            trace_context["parent_span_id"] = parent_span_id
        kwargs["trace_context"] = trace_context
    if model:
        kwargs["model"] = model
    with client.start_as_current_observation(**kwargs) as current:
        yield SpanHandle(current)


def outbound_trace_headers() -> dict[str, str]:
    client = _client()
    if client is None:
        return {}
    trace_id = client.get_current_trace_id()
    parent_id = client.get_current_observation_id()
    headers: dict[str, str] = {}
    if trace_id:
        headers["X-Langfuse-Trace-ID"] = str(trace_id)
    if parent_id:
        headers["X-Langfuse-Parent-ID"] = str(parent_id)
    return headers


def flush() -> None:
    client = _client()
    if client is not None:
        client.flush()
