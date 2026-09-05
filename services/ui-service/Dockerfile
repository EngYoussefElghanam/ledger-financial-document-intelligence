FROM python:3.11-slim

WORKDIR /app

# Build context is the repository root (per README's
# `docker build -f services/ui-service/Dockerfile .`), so paths are
# relative to the repo root, not to services/ui-service/.
COPY services/ui-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/ui-service/app/ .

EXPOSE 7860

CMD ["python", "main.py"]
