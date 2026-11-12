from __future__ import annotations

import argparse
import json
import os
import signal
import time
import socket
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_event(path: Path, event: str, **payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"time": utc_now(), "event": event, **payload}, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def inject_process_failure(
    target_pid: int,
    delay_seconds: float,
    event_log: Path,
    run_id: str,
    target_node: str,
    target_task_id: str | None = None,
    worker_event_log: Path | None = None,
    wait_timeout_seconds: float = 20,
) -> int:
    if target_pid <= 1 or target_pid == os.getpid():
        raise ValueError("target_pid must identify a different, non-system process")
    if delay_seconds < 0 or delay_seconds > 30:
        raise ValueError("delay_seconds must be between 0 and 30")
    if wait_timeout_seconds <= 0 or wait_timeout_seconds > 120:
        raise ValueError("wait_timeout_seconds must be between 0 and 120")
    fields = {
        "run_id": run_id,
        "target_node": target_node,
        "target_pid": target_pid,
        "injection_type": "external_process_termination",
        "scheduled_delay_seconds": delay_seconds,
    }
    if target_task_id:
        fields["target_task_id"] = target_task_id
    append_event(event_log, "injector_armed", **fields)
    worker_started_at = None
    if worker_event_log is not None and target_task_id:
        deadline = time.monotonic() + wait_timeout_seconds
        while time.monotonic() < deadline:
            try:
                lines = worker_event_log.read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []
            for line in reversed(lines):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (
                    record.get("event") == "worker_task_started"
                    and record.get("run_id") == run_id
                    and record.get("task_id") == target_task_id
                ):
                    worker_started_at = record.get("time")
                    break
            if worker_started_at:
                break
            time.sleep(0.02)
        if not worker_started_at:
            raise TimeoutError("target task did not start before the injector wait timeout")
    time.sleep(delay_seconds)
    injected_at = utc_now()
    os.kill(target_pid, signal.SIGTERM)
    append_event(
        event_log,
        "fault_injection_triggered",
        **fields,
        signal="SIGTERM",
        injected_at=injected_at,
        worker_started_at=worker_started_at,
        injector_pid=os.getpid(),
        injector_host=socket.gethostname(),
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independent runtime process-fault injector")
    parser.add_argument("--target-pid", type=int, required=True)
    parser.add_argument("--delay-seconds", type=float, required=True)
    parser.add_argument("--event-log", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--target-node", required=True)
    parser.add_argument("--target-task-id")
    parser.add_argument("--worker-event-log", type=Path)
    parser.add_argument("--wait-timeout-seconds", type=float, default=20)
    args = parser.parse_args(argv)
    try:
        return inject_process_failure(
            args.target_pid, args.delay_seconds, args.event_log, args.run_id,
            args.target_node, args.target_task_id, args.worker_event_log,
            args.wait_timeout_seconds,
        )
    except Exception as exc:
        append_event(args.event_log, "fault_injection_failed", run_id=args.run_id, target_node=args.target_node,
                     target_pid=args.target_pid, error_type=type(exc).__name__, error=str(exc)[:300])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
