from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


SCENARIOS = ("none", "retry-once", "local-recovery")
EXACT_TEST_COMMAND = "python -m pytest test_app.py -q -p no:cacheprovider"
REQUIRED_ARTIFACTS = (
    "workspace/artifacts/software_report.md",
    "workspace/artifacts/code_diff.patch",
    "workspace/artifacts/test_log.txt",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_events(runtime_root: Path) -> list[dict[str, Any]]:
    events_path = runtime_root / "events.jsonl"
    return [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _runtime_root_from_output(output: str) -> Path:
    match = re.search(r"^Runtime root:\s*(.+)$", output, re.MULTILINE)
    if not match:
        raise AssertionError("smoke output does not contain Runtime root")
    return Path(match.group(1).strip())


def _assert_common_success(output: str, runtime_root: Path) -> dict[str, Any]:
    if "Status: completed" not in output:
        raise AssertionError("smoke output does not contain Status: completed")
    phase_match = re.search(r"^Phase count:\s*(\d+)$", output, re.MULTILINE)
    if not phase_match or int(phase_match.group(1)) < 1:
        raise AssertionError("smoke output does not contain a positive Phase count")
    if not runtime_root.is_dir():
        raise AssertionError(f"runtime root does not exist: {runtime_root}")

    state_path = runtime_root / "state.json"
    events_path = runtime_root / "events.jsonl"
    if not state_path.is_file():
        raise AssertionError(f"missing state.json: {state_path}")
    if not events_path.is_file():
        raise AssertionError(f"missing events.jsonl: {events_path}")

    for artifact in REQUIRED_ARTIFACTS:
        path = runtime_root / artifact
        if not path.is_file():
            raise AssertionError(f"missing artifact: {path}")

    report = (runtime_root / "workspace/artifacts/software_report.md").read_text(
        encoding="utf-8"
    )
    if EXACT_TEST_COMMAND not in report:
        raise AssertionError("software report does not contain the exact pytest command")

    state = _load_json(state_path)
    if state.get("status") != "completed":
        raise AssertionError(f"state status is not completed: {state.get('status')}")
    if int(state.get("phase", 0)) < 1:
        raise AssertionError("state phase count is not positive")
    if not state.get("completed_tasks"):
        raise AssertionError("state has no completed_tasks")
    if "failed_tasks" not in state:
        raise AssertionError("state has no failed_tasks")
    if not state.get("last_evaluation"):
        raise AssertionError("state has no acceptance results")
    return state


def _assert_retry_once(output: str, runtime_root: Path) -> None:
    if "implement_fix attempts=2" not in output:
        raise AssertionError("retry-once output does not show implement_fix attempts=2")
    if "structured retry_feedback=" not in output:
        raise AssertionError("retry-once output does not show structured retry_feedback")

    events = _load_events(runtime_root)
    retry_events = [
        event
        for event in events
        if event.get("event") == "retry_summary"
        and event.get("payload", {}).get("task") == "implement_fix"
    ]
    if not retry_events:
        raise AssertionError("retry-once events do not contain retry_summary")
    payload = retry_events[-1]["payload"]
    if payload.get("attempts") != 2:
        raise AssertionError(f"retry_summary attempts != 2: {payload.get('attempts')}")
    feedback = payload.get("retry_feedback")
    if not isinstance(feedback, list) or not feedback:
        raise AssertionError("retry_summary has no structured retry_feedback")
    record = feedback[0]
    if not isinstance(record.get("arguments"), dict):
        raise AssertionError("retry_feedback arguments are not structured")
    if "success" not in record or "metadata" not in record:
        raise AssertionError("retry_feedback record lacks success or metadata")


def _assert_local_recovery(runtime_root: Path) -> None:
    events = _load_events(runtime_root)
    started = [
        event
        for event in events
        if event.get("event") == "local_recovery_started"
    ]
    planned = [
        event
        for event in events
        if event.get("event") == "local_recovery_planned"
    ]
    if not started:
        raise AssertionError("local-recovery has no local_recovery_started event")
    if not planned:
        raise AssertionError("local-recovery has no local_recovery_planned event")

    payload = started[0].get("payload", {})
    frozen = payload.get("frozen", [])
    impacted = payload.get("impacted", [])
    if not frozen:
        raise AssertionError("local recovery did not record frozen nodes")
    if not impacted:
        raise AssertionError("local recovery did not record impacted nodes")
    rerun = [task["id"] for task in planned[0].get("payload", {}).get("tasks", [])]
    repeated_frozen = sorted(set(frozen) & set(rerun))
    if repeated_frozen:
        raise AssertionError(f"local recovery reran frozen nodes: {repeated_frozen}")


def _run_scenario(scenario: str, state_dir: Path) -> Path:
    completed = subprocess.run(
        [
            sys.executable,
            "run_software_demo.py",
            "--fault-scenario",
            scenario,
            "--state-dir",
            str(state_dir),
        ],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise AssertionError(
            f"{scenario} smoke failed with exit_code={completed.returncode}: {output}"
        )

    runtime_root = _runtime_root_from_output(output)
    _assert_common_success(output, runtime_root)
    if scenario == "retry-once":
        _assert_retry_once(output, runtime_root)
    if scenario == "local-recovery":
        _assert_local_recovery(runtime_root)
    print(f"{scenario}: completed; runtime_root={runtime_root}")
    return runtime_root


def main() -> int:
    state_dir = Path(tempfile.mkdtemp(prefix="alternative-frame-software-smoke-"))
    try:
        for scenario in SCENARIOS:
            _run_scenario(scenario, state_dir)
    except Exception as exc:
        print(f"software smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

