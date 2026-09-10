# doc-processor-api Dockerfile
#
# Two things this is deliberately structured around:
# 1. docling downloads its layout/table model weights on first use - we
#    trigger that download during the IMAGE BUILD (via a warmup script),
#    not on container start, so the first real request isn't slow or
#    flaky waiting on a network download.
# 2. shared/ is installed as an editable local package, matching how
#    it's installed in local dev - so imports behave identically in
#    both places.

FROM python:3.11-slim

WORKDIR /service

# System deps docling/OCR commonly need (image processing libs).
# If the build fails looking for a missing .so, this is usually where
# to add it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# --- shared package first (changes less often than app code, so this
# layer stays cached across most rebuilds) ---
COPY shared/ /shared/
RUN pip install --no-cache-dir -e /shared

# --- service dependencies ---
# Install CPU-only torch FIRST. Without this, pip resolves docling's
# torch dependency with full CUDA/GPU support by default — pulling in
# several GB of NVIDIA libraries (cudnn, cublas, nccl, etc.) that this
# service never uses, since docling/RapidOCR run on CPU here. Installing
# the CPU wheel first satisfies the version constraint before docling's
# install step ever looks for a GPU build.
RUN pip install --no-cache-dir \
    torch==2.5.1 torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cpu

COPY services/doc-processor-api/requirements.txt .

RUN pip freeze | grep -E '^(torch|torchvision)==' > /tmp/torch-constraints.txt && \
    pip install --no-cache-dir --default-timeout=180 --retries=5 \
    -c /tmp/torch-constraints.txt -r requirements.txt

# --- warm up docling's models at BUILD time, not first request ---
# This forces docling to download and cache its layout/table model
# weights into the image itself.
COPY services/doc-processor-api/app/warmup.py .
RUN python warmup.py

# --- service code ---
COPY services/doc-processor-api/app/ ./app/

# Where processed output + uploaded PDFs get persisted. In docker-compose
# this should be mounted as a volume shared with retrieval-api, so it can
# read ProcessedDocument JSON without hitting this service's API.
RUN mkdir -p data/processed data/uploads

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
