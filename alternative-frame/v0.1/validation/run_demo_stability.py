"""Run the frozen research and software demos three consecutive times each."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import time
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from run_research_demo import run_demo as run_research_demo  # noqa: E402
from run_software_demo import run_demo as run_software_demo  # noqa: E402


RESEARCH_SOURCES = (
    "generate_dataset.py",
    "run_baseline.py",
    "run_improved.py",
    "verify_best.py",
)
RESEARCH_ARTIFACTS = (
    "artifacts/baseline_metrics.json",
    "artifacts/improved_metrics.json",
    "artifacts/verification_metrics.json",
    "artifacts/comparison.png",
    "artifacts/research_report.md",
)
SOFTWARE_ARTIFACTS = (
    "workspace/artifacts/software_report.md",
    "workspace/artifacts/code_diff.patch",
    "workspace/artifacts/test_log.txt",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_files(root: Path, names: tuple[str, ...]) -> dict[str, str]:
    missing = [name for name in names if not (root / name).is_file()]
    if missing:
        raise RuntimeError(f"missing artifacts under {root}: {missing}")
    return {name: _sha256(root / name) for name in names}


def _read_events(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_research(output_root: Path, index: int) -> dict[str, Any]:
    workspace = output_root / "research" / f"run-{index}" / "workspace"
    runtime = output_root / "research" / f"run-{index}" / "runtime"
    workspace.mkdir(parents=True)
    source = PROJECT_ROOT / "examples" / "research_task"
    for name in RESEARCH_SOURCES:
        shutil.copy2(source / name, workspace / name)

    run_id = f"research-stability-{index}"
    started = time.perf_counter()
    report = run_research_demo(
        workspace,
        runtime,
        run_id,
        fault_scenario="normal",
    )
    duration = time.perf_counter() - started
    run_root = runtime / run_id
    state_path = run_root / "state.json"
    events_path = run_root / "events.jsonl"
    hashes = _verify_files(workspace, RESEARCH_ARTIFACTS)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    events = _read_events(events_path)
    if report.status != "completed" or state.get("status") != "completed":
        raise RuntimeError(f"research run {index} did not complete")
    if int(state.get("phase", 0)) != 2:
        raise RuntimeError(f"research run {index} expected 2 phases")
    if not any(event.get("event") == "run_completed" for event in events):
        raise RuntimeError(f"research run {index} has no run_completed event")
    return {
        "domain": "research",
        "run": index,
        "status": "completed",
        "scenario": "normal",
        "phases": state["phase"],
        "tasks": state.get("total_tasks"),
        "duration_seconds": round(duration, 6),
        "state": str(state_path),
        "events": str(events_path),
        "event_count": len(events),
        "artifact_sha256": hashes,
    }


def _run_software(output_root: Path, index: int) -> dict[str, Any]:
    runtime = output_root / "software" / f"run-{index}" / "runtime"
    stdout = io.StringIO()
    stderr = io.StringIO()
    started = time.perf_counter()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = run_software_demo("none", str(runtime))
    duration = time.perf_counter() - started
    candidates = [path for path in runtime.iterdir() if path.is_dir()]
    if exit_code != 0 or len(candidates) != 1:
        detail = (stdout.getvalue() + stderr.getvalue()).strip()
        raise RuntimeError(f"software run {index} failed: {detail}")
    run_root = candidates[0]
    state_path = run_root / "state.json"
    events_path = run_root / "events.jsonl"
    hashes = _verify_files(run_root, SOFTWARE_ARTIFACTS)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    events = _read_events(events_path)
    if state.get("status") != "completed":
        raise RuntimeError(f"software run {index} did not complete")
    if int(state.get("phase", 0)) != 2:
        raise RuntimeError(f"software run {index} expected 2 phases")
    if not any(event.get("event") == "run_completed" for event in events):
        raise RuntimeError(f"software run {index} has no run_completed event")
    return {
        "domain": "software",
        "run": index,
        "status": "completed",
        "scenario": "none",
        "phases": state["phase"],
        "tasks": state.get("total_tasks"),
        "duration_seconds": round(duration, 6),
        "state": str(state_path),
        "events": str(events_path),
        "event_count": len(events),
        "artifact_sha256": hashes,
    }


def _write_summary(output_root: Path, records: list[dict[str, Any]]) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "schema_version": "1.0",
        "generated_at": generated_at,
        "required_runs_per_domain": 3,
        "overall_status": "passed",
        "records": records,
    }
    (output_root / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Dual Demo Consecutive Stability Report",
        "",
        f"- Generated at: `{generated_at}`",
        "- Acceptance: Research Demo 3/3 completed; Software Demo 3/3 completed.",
        "- Isolation: every run used a new workspace and runtime directory.",
        "",
        "| Domain | Run | Scenario | Status | Phases | Tasks | Duration (s) | Events |",
        "|---|---:|---|---|---:|---:|---:|---:|",
    ]
    for row in records:
        lines.append(
            f"| {row['domain']} | {row['run']} | {row['scenario']} | {row['status']} | "
            f"{row['phases']} | {row['tasks']} | {row['duration_seconds']} | {row['event_count']} |"
        )
    lines.extend(
        [
            "",
            "Each record in `summary.json` contains absolute evidence paths and SHA-256 hashes for required artifacts.",
        ]
    )
    (output_root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Evidence directory (default: reports/demo-stability/<UTC timestamp>).",
    )
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root = (args.output_dir or PROJECT_ROOT / "reports" / "demo-stability" / stamp).resolve()
    if output_root.exists():
        raise SystemExit(f"output directory already exists: {output_root}")
    output_root.mkdir(parents=True)

    records: list[dict[str, Any]] = []
    try:
        for index in range(1, 4):
            record = _run_research(output_root, index)
            records.append(record)
            print(f"research {index}/3: completed ({record['duration_seconds']}s)")
        for index in range(1, 4):
            record = _run_software(output_root, index)
            records.append(record)
            print(f"software {index}/3: completed ({record['duration_seconds']}s)")
    except Exception as exc:
        failure = {
            "schema_version": "1.0",
            "overall_status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "records": records,
        }
        (output_root / "summary.json").write_text(
            json.dumps(failure, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"FAILED: {failure['error']}", file=sys.stderr)
        print(f"evidence={output_root}")
        return 1

    _write_summary(output_root, records)
    print("overall: passed (research=3/3, software=3/3)")
    print(f"evidence={output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

