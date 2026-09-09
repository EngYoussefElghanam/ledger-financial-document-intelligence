FROM python:3.11-slim AS core
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /workspace
COPY docker/requirements-core.txt /tmp/requirements-core.txt
RUN pip install -r /tmp/requirements-core.txt
COPY shared/ /workspace/shared/
RUN pip install /workspace/shared
COPY services/ /workspace/services/

# Processor and retrieval share one CPU-only image. No dataset or model
# weights are downloaded during the build; models use a persisted runtime cache.
FROM core AS ml
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN pip install docling qdrant-client fastembed sentence-transformers

FROM core AS agent
RUN pip install langgraph langchain-core langchain-groq langchain-google-genai python-dotenv numexpr
