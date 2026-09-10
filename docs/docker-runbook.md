# Running LEDGER with Docker Desktop

Use Linux containers in Docker Desktop. Run these commands from the repository
root in VS Code's Command Prompt terminal. No command below downloads TAT-DQA.
Compose uses `docker/Dockerfile`; the older per-service Dockerfiles are not
used by this setup.

## Start the small services

```bat
docker compose up -d --build answer-validator-api orchestrator-api ui-service
docker compose ps
```

Open http://localhost:7860. This starts the actual UI, orchestrator, and
validator with mocks disabled. Without the processor, retrieval, and agent,
the UI can open but cannot answer document questions. Requests return a
dependency error rather than canned answers. An empty corpus is expected.

## Start the complete pipeline

First free sufficient disk space for CPU PyTorch, Docling, embeddings, their
build layers, and runtime model caches. Allow substantially more than the
6.8 GiB that was available when this setup was prepared; actual requirements
depend on resolved package and model versions. Do not delete unrelated Docker
images or volumes to make room without checking what uses them.

Set `GROQ_API_KEY` in the root `.env`. The key is passed only to the agent;
`.env`, datasets, local environments, and local databases are excluded from
the build context. Docker overrides local `localhost` service URLs with
Compose service names and forces both mock switches off.

```bat
docker compose build doc-processor-api
docker compose build agent-service
docker compose up -d
docker compose ps
docker compose logs --tail 50 retrieval-api agent-service
```

The processor and retrieval share `ledger-ml:local`, so build that image only
once. PyTorch is installed from the CPU wheel index. Model weights are fetched
at runtime on first use; this is separate from the dataset and still requires
disk space and internet access. Retrieval's startup health check allows time
for its initial downloads. The agent waits for retrieval to become healthy.

After all six containers are healthy, you may ingest a PDF you already have
through http://localhost:8000/docs (`POST /documents/ingest`), supplying an
optional dataset ID. Downloading the full dataset is not required to run a
single-document demo.

## Ports and persistent storage

| Service | Local URL |
|---|---|
| UI | http://localhost:7860 |
| Orchestrator | http://localhost:8000/docs |
| Processor | http://localhost:8001/docs |
| Retrieval | http://localhost:8002/docs |
| Agent | http://localhost:8003/docs |
| Validator | http://localhost:8004/docs |

Named volumes preserve processed PDFs/JSON, Qdrant storage, the corpus
manifest, and model caches. These are separate from existing host-run data;
this setup does not import or modify your existing host corpus. HTTP ports
bind only to the local machine.

```bat
docker compose stop
docker compose start
```

To remove the containers while retaining data:

```bat
docker compose down
```

Do not add `--volumes` unless you intend to delete the persisted corpus and
model caches. To rebuild after code changes, repeat the appropriate build and
`up -d` command.
