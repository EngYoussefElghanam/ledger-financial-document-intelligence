"""Durable, atomic local storage for evaluation runs."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from app.models import RunSummary


class RunStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manifest_dir = self.root / "manifests"
        self.run_dir = self.root / "runs"
        self.manifest_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @staticmethod
    def _atomic_json(path: Path, payload: Any) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)

    def manifest_path(self, manifest_id: str) -> Path:
        return self.manifest_dir / f"{manifest_id}.json"

    def create_run(self, summary: RunSummary, config: dict[str, Any]) -> Path:
        path = self.run_dir / summary.run_id
        path.mkdir(parents=True, exist_ok=False)
        self._atomic_json(path / "status.json", summary.model_dump(mode="json"))
        self._atomic_json(path / "config.json", config)
        return path

    def read_status(self, run_id: str) -> RunSummary:
        path = self.run_dir / run_id / "status.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        return RunSummary.model_validate_json(path.read_text(encoding="utf-8"))

    def write_status(self, summary: RunSummary) -> None:
        self._atomic_json(
            self.run_dir / summary.run_id / "status.json",
            summary.model_dump(mode="json"),
        )

    def append_item(self, run_id: str, item: dict[str, Any]) -> None:
        line = json.dumps(item, ensure_ascii=False) + "\n"
        with self._lock:
            with (self.run_dir / run_id / "items.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(line)
                stream.flush()
                os.fsync(stream.fileno())

    def read_items(self, run_id: str) -> list[dict[str, Any]]:
        path = self.run_dir / run_id / "items.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]

    def write_artifact(self, run_id: str, filename: str, payload: Any) -> Path:
        path = self.run_dir / run_id / filename
        self._atomic_json(path, payload)
        return path

    def write_text_artifact(self, run_id: str, filename: str, text: str) -> Path:
        path = self.run_dir / run_id / filename
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
        return path

    def read_config(self, run_id: str) -> dict[str, Any]:
        path = self.run_dir / run_id / "config.json"
        if not path.exists():
            raise FileNotFoundError(run_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def artifacts(self, run_id: str) -> dict[str, str]:
        path = self.run_dir / run_id
        if not path.exists():
            raise FileNotFoundError(run_id)
        return {entry.name: str(entry.resolve()) for entry in sorted(path.iterdir()) if entry.is_file()}
