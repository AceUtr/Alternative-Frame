from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SCENARIOS = ("none", "retry-once", "local-recovery")
EXACT_TEST_COMMAND = "python -m pytest test_app.py -q -p no:cacheprovider"
REQUIRED_ARTIFACTS = (
    "workspace/artifacts/software_report.md",
    "workspace/artifacts/code_diff.patch",
    "workspace/artifacts/test_log.txt",
)


def _runtime_root(output: str) -> Path:
    match = re.search(r"^Runtime root:\s*(.+)$", output, re.MULTILINE)
    if not match:
        raise AssertionError("missing Runtime root output")
    return Path(match.group(1).strip())


def _events(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in (path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _check(scenario: str, output: str, root: Path) -> None:
    if "Status: completed" not in output:
        raise AssertionError(f"{scenario}: status is not completed")
    if not root.is_dir():
        raise AssertionError(f"{scenario}: runtime root does not exist")

    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "run_manifest.json").read_text(encoding="utf-8"))
    if state.get("status") != "completed":
        raise AssertionError(f"{scenario}: state is not completed")
    if manifest.get("run_id") != root.name:
        raise AssertionError(f"{scenario}: manifest run_id mismatch")
    if manifest.get("scenario") != scenario:
        raise AssertionError(f"{scenario}: manifest scenario mismatch")
    if manifest.get("test_command") != EXACT_TEST_COMMAND:
        raise AssertionError(f"{scenario}: exact test command mismatch")
    if manifest.get("test_exit_code") != 0 or manifest.get("process_exit_code") != 0:
        raise AssertionError(f"{scenario}: manifest contains a nonzero exit code")
    for artifact in REQUIRED_ARTIFACTS:
        if not (root / artifact).is_file():
            raise AssertionError(f"{scenario}: missing {artifact}")

    events = _events(root)
    if scenario == "retry-once" and not any(
        item.get("event") == "task_retry_scheduled" for item in events
    ):
        raise AssertionError("retry-once: missing task_retry_scheduled")
    if scenario == "local-recovery" and not any(
        item.get("event") == "local_recovery_started" for item in events
    ):
        raise AssertionError("local-recovery: missing local_recovery_started")


def main() -> int:
    state_dir = Path(tempfile.mkdtemp(prefix="alternative-frame-v1.1-software-smoke-"))
    try:
        for scenario in SCENARIOS:
            completed = subprocess.run(
                [
                    sys.executable,
                    "run_software_demo.py",
                    "--fault-scenario",
                    scenario,
                    "--runs-dir",
                    str(state_dir),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                timeout=180,
            )
            output = (completed.stdout or "") + (completed.stderr or "")
            if completed.returncode != 0:
                raise AssertionError(f"{scenario}: exit_code={completed.returncode}\n{output}")
            root = _runtime_root(output)
            _check(scenario, output, root)
            print(f"{scenario}: completed; runtime_root={root}")
    except Exception as exc:
        print(f"software smoke failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
