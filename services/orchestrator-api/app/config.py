"""
Downstream service URLs, one place to change them for local dev vs Docker.
In Docker Compose these get overridden via environment variables to use
service names instead of localhost (e.g. http://doc-processor-api:8001).
"""

import os

DOC_PROCESSOR_URL = os.getenv("DOC_PROCESSOR_URL", "http://localhost:8001")
RETRIEVAL_URL = os.getenv("RETRIEVAL_URL", "http://localhost:8002")
AGENT_SERVICE_URL = os.getenv("AGENT_SERVICE_URL", "http://localhost:8003")
ANSWER_VALIDATOR_URL = os.getenv("ANSWER_VALIDATOR_URL", "http://localhost:8004")