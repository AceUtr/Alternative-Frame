"""Workspace-scoped dataset inspection for the offline research fixture."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from core.tools import Tool, ToolResult


class DatasetInspector(Tool):
    name = "dataset_inspector"

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve()

    def _resolve(self, value: object) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("path must be a non-empty relative string")
        relative = Path(value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"path escapes workspace: {value}")
        target = (self.workspace / relative).resolve()
        if target != self.workspace and self.workspace not in target.parents:
            raise ValueError(f"path escapes workspace: {value}")
        return target

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Validate a generated train/test JSON dataset",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dataset_path": {"type": "string"},
                        "output_path": {"type": "string"},
                        "required_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["dataset_path", "output_path"],
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            dataset_path = self._resolve(arguments.get("dataset_path"))
            output_path = self._resolve(arguments.get("output_path"))
        except ValueError as exc:
            return ToolResult(self.name, False, error=str(exc))
        required = arguments.get("required_fields", ["x1", "x2", "label"])
        if not isinstance(required, list) or not required or not all(
            isinstance(item, str) and item for item in required
        ):
            return ToolResult(self.name, False, error="required_fields must be non-empty strings")
        if not dataset_path.is_file():
            return ToolResult(self.name, False, error=f"dataset not found: {arguments['dataset_path']}")
        try:
            payload = json.loads(dataset_path.read_text(encoding="utf-8"))
            train = payload["train"]
            test = payload["test"]
            rows = list(train) + list(test)
            if not train or not test:
                raise ValueError("train and test splits must be non-empty")
            for index, row in enumerate(rows):
                missing = sorted(set(required) - set(row))
                if missing:
                    raise ValueError(f"row {index} missing fields: {missing}")
            summary = {
                "dataset_version": payload.get("metadata", {}).get("dataset_version"),
                "seed": payload.get("metadata", {}).get("seed"),
                "rows": len(rows),
                "train_rows": len(train),
                "test_rows": len(test),
                "columns": sorted(rows[0]),
                "label_distribution": dict(
                    sorted(Counter(str(row["label"]) for row in rows).items())
                ),
            }
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return ToolResult(self.name, False, error=f"invalid dataset: {exc}")
        relative_output = output_path.relative_to(self.workspace).as_posix()
        return ToolResult(
            self.name,
            True,
            output=f"inspected {len(rows)} rows",
            metadata={
                "artifacts": [relative_output],
                "dataset": summary,
            },
        )
