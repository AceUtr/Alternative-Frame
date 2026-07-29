"""Compare run-provenanced metric JSON files inside one workspace."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from core.tools import Tool, ToolResult


class MetricComparator(Tool):
    name = "metric_comparator"

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
                "description": "Select the best experiment from compatible metric JSON files",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric_files": {"type": "array", "items": {"type": "string"}},
                        "primary_metric": {"type": "string"},
                        "mode": {"type": "string", "enum": ["max", "min"]},
                        "output_path": {"type": "string"},
                    },
                    "required": ["metric_files", "primary_metric", "mode", "output_path"],
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            paths = [self._resolve(value) for value in arguments.get("metric_files", [])]
            output = self._resolve(arguments.get("output_path"))
        except ValueError as exc:
            return ToolResult(self.name, False, error=str(exc))
        if len(paths) < 2:
            return ToolResult(self.name, False, error="at least two metric files are required")
        metric_name = arguments.get("primary_metric")
        mode = arguments.get("mode")
        if mode not in {"max", "min"}:
            return ToolResult(self.name, False, error=f"invalid comparison mode: {mode}")
        try:
            records = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
            versions = {record["dataset_version"] for record in records}
            seeds = {record["seed"] for record in records}
            metric_names = {record["metric_name"] for record in records}
            if len(versions) != 1 or len(seeds) != 1 or metric_names != {metric_name}:
                raise ValueError("metric files use incompatible dataset, seed, or metric")
            for record in records:
                value = record.get(metric_name)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise ValueError(f"invalid numeric metric: {metric_name}")
                if not math.isfinite(float(value)):
                    raise ValueError(f"non-finite metric: {metric_name}")
            selector = max if mode == "max" else min
            best = selector(records, key=lambda record: float(record[metric_name]))
            best_config = {
                "best_experiment": best["experiment"],
                "primary_metric": metric_name,
                "mode": mode,
                "best_score": float(best[metric_name]),
                "dataset_version": best["dataset_version"],
                "seed": best["seed"],
                "features_used": list(best["features_used"]),
                "source_metrics": paths[records.index(best)].relative_to(self.workspace).as_posix(),
                "candidates": [
                    {"experiment": record["experiment"], "score": float(record[metric_name])}
                    for record in records
                ],
            }
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(best_config, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return ToolResult(self.name, False, error=f"metric comparison failed: {exc}")
        artifact = output.relative_to(self.workspace).as_posix()
        return ToolResult(
            self.name,
            True,
            output=f"selected {best_config['best_experiment']}",
            metadata={
                "artifacts": [artifact],
                "metrics": {"best_score": best_config["best_score"]},
                "best_experiment": best_config["best_experiment"],
            },
        )
