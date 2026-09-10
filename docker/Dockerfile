FROM node:22-slim AS ui-assets
WORKDIR /ui
COPY services/ui-service/package.json services/ui-service/package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.11-slim AS dependencies
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /workspace
COPY docker/requirements-core.txt /tmp/requirements-core.txt
RUN pip install -r /tmp/requirements-core.txt
COPY shared/ /workspace/shared/
RUN pip install /workspace/shared

FROM dependencies AS core
COPY services/ /workspace/services/
COPY --from=ui-assets /ui/node_modules/pdfjs-dist /workspace/services/ui-service/node_modules/pdfjs-dist

# Processor and retrieval share one CPU-only image. No dataset or model
# weights are downloaded during the build; models use a persisted runtime cache.
FROM dependencies AS ml
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
RUN --mount=type=cache,target=/root/.cache/pip PIP_NO_CACHE_DIR=false pip install --retries 10 --timeout 120 torch torchvision --index-url https://download.pytorch.org/whl/cpu
RUN --mount=type=cache,target=/root/.cache/pip PIP_NO_CACHE_DIR=false pip install --retries 10 --timeout 120 docling qdrant-client fastembed sentence-transformers
COPY services/ /workspace/services/

FROM dependencies AS agent
RUN pip install langgraph langchain-core langchain-groq langchain-google-genai python-dotenv numexpr
COPY services/ /workspace/services/

FROM dependencies AS eval
RUN pip install "langfuse>=4,<5"
COPY services/ /workspace/services/
