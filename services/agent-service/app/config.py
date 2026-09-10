"""Repository-root configuration shared by the agent modules."""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT_DIR / ".env"

if ENV_PATH.exists():
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

RETRIEVAL_API_URL = os.getenv("RETRIEVAL_API_URL", "http://localhost:8002")
AGENT_MODEL = os.getenv("AGENT_MODEL", "qwen/qwen3.8-27b")
AGENT_PROVIDER = os.getenv("AGENT_PROVIDER", "groq")
AGENT_PROMPT_VERSION = os.getenv("AGENT_PROMPT_VERSION", "graph-v1")
LLM_INPUT_COST_PER_MILLION = float(os.getenv("LLM_INPUT_COST_PER_MILLION", "0"))
LLM_OUTPUT_COST_PER_MILLION = float(os.getenv("LLM_OUTPUT_COST_PER_MILLION", "0"))
LLM_PRICE_SOURCE = os.getenv("LLM_PRICE_SOURCE", "unconfigured")
LLM_PRICE_EFFECTIVE_DATE = os.getenv("LLM_PRICE_EFFECTIVE_DATE", "unconfigured")
