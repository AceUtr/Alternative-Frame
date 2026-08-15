"""Workspace-scoped dataset inspection for the offline research fixture."""

from __future__ import annotations

import hashlib
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
                        "field_types": {"type": "object"},
                        "allowed_labels": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                        "required_provenance": {
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
        field_types = arguments.get(
            "field_types",
            {"id": "integer", "x1": "number", "x2": "number", "label": "integer"},
        )
        allowed_labels = arguments.get("allowed_labels", [0, 1])
        required_provenance = arguments.get(
            "required_provenance", ["source", "generator", "license"]
        )
        if not isinstance(required, list) or not required or not all(
            isinstance(item, str) and item for item in required
        ):
            return ToolResult(self.name, False, error="required_fields must be non-empty strings")
        if not dataset_path.is_file():
            return ToolResult(self.name, False, error=f"dataset not found: {arguments['dataset_path']}")
        try:
            payload = json.loads(dataset_path.read_text(encoding="utf-8"))
            metadata = payload["metadata"]
            provenance = metadata["provenance"]
            missing_provenance = sorted(set(required_provenance) - set(provenance))
            if missing_provenance:
                raise ValueError(f"provenance missing fields: {missing_provenance}")
            train = payload["train"]
            test = payload["test"]
            rows = list(train) + list(test)
            if not train or not test:
                raise ValueError("train and test splits must be non-empty")
            for index, row in enumerate(rows):
                missing = sorted(set(required) - set(row))
                if missing:
                    raise ValueError(f"row {index} missing fields: {missing}")
                for field, expected_type in field_types.items():
                    if field not in row:
                        raise ValueError(f"row {index} missing typed field: {field}")
                    value = row[field]
                    valid = {
                        "integer": isinstance(value, int) and not isinstance(value, bool),
                        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
                        "string": isinstance(value, str),
                    }.get(expected_type)
                    if valid is None:
                        raise ValueError(f"unsupported field type: {expected_type}")
                    if not valid:
                        raise ValueError(
                            f"row {index} field {field} must be {expected_type}"
                        )
                if row["label"] not in allowed_labels:
                    raise ValueError(f"row {index} has invalid label: {row['label']}")
            ids = [row["id"] for row in rows]
            if len(ids) != len(set(ids)):
                raise ValueError("dataset ids must be unique")
            summary = {
                "dataset_version": metadata.get("dataset_version"),
                "seed": metadata.get("seed"),
                "provenance": provenance,
                "sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
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
