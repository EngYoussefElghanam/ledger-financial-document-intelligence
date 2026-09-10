"""
Downstream service URLs, one place to change them for local dev vs Docker.
In Docker Compose these get overridden via environment variables to use
service names instead of localhost (e.g. http://doc-processor-api:8001).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env", override=False)

DOC_PROCESSOR_URL = os.getenv("DOC_PROCESSOR_URL", "http://localhost:8001")
RETRIEVAL_URL = os.getenv("RETRIEVAL_URL", "http://localhost:8002")
AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://localhost:8003")
ANSWER_VALIDATOR_URL = os.getenv("ANSWER_VALIDATOR_URL", "http://localhost:8004")
USE_MOCK_AGENT = os.getenv("USE_MOCK_AGENT", "false").lower() == "true"
CORPUS_MANIFEST_PATH = Path(
    os.getenv("CORPUS_MANIFEST_PATH", str(ROOT_DIR / "data" / "corpus-manifest.json"))
)
