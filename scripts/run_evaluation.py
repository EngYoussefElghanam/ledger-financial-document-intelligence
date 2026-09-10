"""Submit an eval-service run and wait for terminal status."""

from __future__ import annotations

import argparse
import time

import httpx


TERMINAL = {"completed", "completed_with_errors", "failed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest_path")
    parser.add_argument("--eval-url", default="http://localhost:8005")
    parser.add_argument("--variant", choices=["reranker_on", "reranker_off"], default="reranker_on")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--require-langfuse", action="store_true")
    args = parser.parse_args()

    payload = {
        "manifest_path": args.manifest_path,
        "variant": args.variant,
        "concurrency": args.concurrency,
        "max_items": args.max_items,
        "require_langfuse": args.require_langfuse,
    }
    response = httpx.post(f"{args.eval_url}/runs", json=payload, timeout=30)
    if not response.is_success:
        print(f"Evaluation not started (HTTP {response.status_code}): {response.text}")
        return 1
    response.raise_for_status()
    created = response.json()
    run_id = created["run_id"]
    print(f"run_id={run_id}")

    while True:
        status = httpx.get(f"{args.eval_url}/runs/{run_id}", timeout=30).json()
        print(
            f"status={status['status']} completed={status['completed']}/"
            f"{status['attempted']} failed={status['failed']}"
        )
        if status["status"] in TERMINAL:
            break
        time.sleep(2)

    if status["status"] == "failed":
        print(status.get("error") or "evaluation failed")
        return 1
    metrics = httpx.get(f"{args.eval_url}/runs/{run_id}/metrics", timeout=30).json()
    artifacts = httpx.get(f"{args.eval_url}/runs/{run_id}/artifacts", timeout=30).json()
    print(metrics)
    print(artifacts)
    return 1 if status["status"] == "completed_with_errors" else 0


if __name__ == "__main__":
    raise SystemExit(main())
