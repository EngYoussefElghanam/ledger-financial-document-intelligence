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
