"""Build a dependency-free PNG comparison chart and Markdown research report."""

from __future__ import annotations

import json
import math
import struct
import zlib
from pathlib import Path
from typing import Any

from core.tools import Tool, ToolResult


class ResearchReportBuilder(Tool):
    name = "research_report_builder"

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
                "description": "Generate a metric comparison PNG and Markdown report",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "baseline_metrics_path": {"type": "string"},
                        "improved_metrics_path": {"type": "string"},
                        "best_config_path": {"type": "string"},
                        "verification_metrics_path": {"type": "string"},
                        "chart_path": {"type": "string"},
                        "report_path": {"type": "string"},
                    },
                    "required": [
                        "baseline_metrics_path",
                        "improved_metrics_path",
                        "best_config_path",
                        "verification_metrics_path",
                        "chart_path",
                        "report_path",
                    ],
                },
            },
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            baseline_path = self._resolve(arguments.get("baseline_metrics_path"))
            improved_path = self._resolve(arguments.get("improved_metrics_path"))
            best_path = self._resolve(arguments.get("best_config_path"))
            verification_path = self._resolve(arguments.get("verification_metrics_path"))
            chart_path = self._resolve(arguments.get("chart_path"))
            report_path = self._resolve(arguments.get("report_path"))
            baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
            improved = json.loads(improved_path.read_text(encoding="utf-8"))
            best = json.loads(best_path.read_text(encoding="utf-8"))
            verification = (
                json.loads(verification_path.read_text(encoding="utf-8"))
                if verification_path.is_file()
                else None
            )
            if baseline["dataset_version"] != improved["dataset_version"]:
                raise ValueError("report metrics use different dataset versions")
            if baseline["seed"] != improved["seed"]:
                raise ValueError("report metrics use different seeds")
            baseline_score = float(baseline["accuracy"])
            improved_score = float(improved["accuracy"])
            if not math.isfinite(baseline_score) or not math.isfinite(improved_score):
                raise ValueError("report accuracy metrics must be finite")
            scores = [baseline_score, improved_score]
            labels = [baseline["experiment"], improved["experiment"]]
            if verification is not None:
                verification_score = float(verification["accuracy"])
                if not math.isfinite(verification_score):
                    raise ValueError("verification accuracy must be finite")
                scores.append(verification_score)
                labels.append("independent_verification")
            self._write_chart(chart_path, scores)
            delta = improved_score - baseline_score
            outcome = "improved" if delta > 0 else "tied" if delta == 0 else "regressed"
            verification_status = "pending"
            if verification is not None:
                verification_status = "passed" if (
                    verification.get("verification_passed") is True
                    and abs(
                        float(verification["accuracy"]) - float(best["best_score"])
                    ) <= float(verification["verification_tolerance"])
                ) else "failed"
            rows = "\n".join(
                f"| {label} | {score:.6f} |" for label, score in zip(labels, scores)
            )
            report = (
                "# Offline Research Demo Report\n\n"
                f"- Dataset: `{baseline['dataset_version']}`\n"
                f"- Seed: `{baseline['seed']}`\n"
                f"- Primary metric: `accuracy` (higher is better)\n"
                f"- Selected experiment: `{best['best_experiment']}`\n"
                f"- Candidate outcome: **{outcome}** (`delta={delta:.6f}`)\n"
                f"- Independent verification: **{verification_status}**\n\n"
                "| Experiment | Accuracy |\n| --- | ---: |\n"
                f"{rows}\n\n"
                "![Metric comparison](comparison.png)\n"
            )
            chart_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(report, encoding="utf-8")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return ToolResult(self.name, False, error=f"report generation failed: {exc}")
        artifacts = [
            chart_path.relative_to(self.workspace).as_posix(),
            report_path.relative_to(self.workspace).as_posix(),
        ]
        return ToolResult(
            self.name,
            True,
            output=f"report generated; verification={verification_status}",
            metadata={
                "artifacts": artifacts,
                "metrics": {"improvement_delta": delta},
                "verification_status": verification_status,
            },
        )

    @staticmethod
    def _write_chart(path: Path, scores: list[float]) -> None:
        width, height = 360, 240
        pixels = [[(248, 250, 252) for _ in range(width)] for _ in range(height)]
        colors = [(74, 120, 196), (55, 158, 96), (232, 151, 45)]
        bar_width = 60
        gap = (width - len(scores) * bar_width) // (len(scores) + 1)
        for index, score in enumerate(scores):
            bar_height = max(1, min(180, round(float(score) * 180)))
            left = gap + index * (bar_width + gap)
            top = height - 30 - bar_height
            for y in range(top, height - 30):
                for x in range(left, left + bar_width):
                    pixels[y][x] = colors[index % len(colors)]
        raw = b"".join(b"\x00" + bytes(channel for pixel in row for channel in pixel) for row in pixels)

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b"")
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
