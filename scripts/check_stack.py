"""Check local services, corpus coverage, and evaluation prerequisites."""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx


def check(name, url):
    try:
        response = httpx.get(url, timeout=8)
        response.raise_for_status()
        data = response.json() if name != "ui" else {"status": "ok"}
        return name, {"reachable": True, **data}
    except (httpx.HTTPError, ValueError) as error:
        return name, {"reachable": False, "error": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    targets = [(name, f"http://127.0.0.1:{port}/health") for name, port in
               [("orchestrator", 8006), ("processor", 8001), ("retrieval", 8002),
                ("agent", 8003), ("validator", 8004), ("evaluator", 8005)]]
    targets.extend([("ui", "http://127.0.0.1:7860/"),
                    ("readiness", "http://127.0.0.1:8006/ready"),
                    ("corpus", "http://127.0.0.1:8006/ingestion")])
    with ThreadPoolExecutor(max_workers=9) as executor:
        checks = dict(executor.map(lambda target: check(*target), targets))
    corpus = checks["corpus"]
    indexed = {item["document_id"] for item in corpus.pop("documents", [])
               if item.get("status") == "indexed"}
    success = all(value["reachable"] for value in checks.values())
    success = success and checks["readiness"].get("ready", False)
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        required = {doc for item in manifest["items"] for doc in item["document_ids"]}
        missing = sorted(required - indexed)
        checks["evaluation_corpus"] = {"required": len(required),
                                       "indexed": len(required & indexed),
                                       "missing_ids": missing}
        success = success and not missing
    print(json.dumps(checks, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
