# Architecture

## Service ports (local dev)

| Service              | Port |
| -------------------- | ---- |
| orchestrator-api     | 8006 |
| doc-processor-api    | 8001 |
| retrieval-api        | 8000 |
| agent-service        | 8003 |
| answer-validator-api | 8004 |
| eval-service         | 8005 |
| ui-service (Gradio)  | 7860 |

## Request flow for a question

UI --POST /ask--> orchestrator-api --> agent-service (retrieves + reasons)
--> orchestrator-api --POST /validate_answer--> answer-validator-api
--> orchestrator-api --> UI
