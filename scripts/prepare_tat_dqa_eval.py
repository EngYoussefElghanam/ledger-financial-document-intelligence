"""Create a deterministic LEDGER evaluation manifest from TAT-DQA JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
EVAL_SERVICE_DIR = ROOT_DIR / "services" / "eval-service"
sys.path.insert(0, str(EVAL_SERVICE_DIR))

from app.dataset import build_manifest, write_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Official or flat TAT-DQA JSON")
    parser.add_argument("--name", default="tat-dqa-held-out")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--split", default="held_out")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = build_manifest(
        args.source,
        name=args.name,
        seed=args.seed,
        selection_fraction=args.fraction,
        max_items=args.max_items,
        split=args.split,
    )
    output = args.output or (
        ROOT_DIR / "data" / "evaluation" / "manifests" / f"{manifest.manifest_id}.json"
    )
    path = write_manifest(manifest, output)
    print(f"manifest_id={manifest.manifest_id}")
    print(f"items={len(manifest.items)}")
    print(f"source_sha256={manifest.source_sha256}")
    print(f"path={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

