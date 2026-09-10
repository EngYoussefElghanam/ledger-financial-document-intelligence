"""Configuration for the evaluation service."""

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env", override=False)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8000").rstrip("/")
EVAL_DATA_DIR = Path(
    os.getenv("EVAL_DATA_DIR", str(ROOT_DIR / "data" / "evaluation"))
).resolve()
DEFAULT_DATASET_PATH = Path(
    os.getenv(
        "EVAL_DATASET_PATH",
        str(ROOT_DIR / "data" / "questions_setA_practice.json"),
    )
).resolve()
LANGFUSE_REQUIRED = os.getenv("LANGFUSE_REQUIRED", "false").lower() == "true"

