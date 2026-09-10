#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$repo_dir"

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example; add GROQ/Langfuse credentials as needed."
fi

docker compose config --quiet
exec docker compose up --build "$@"
