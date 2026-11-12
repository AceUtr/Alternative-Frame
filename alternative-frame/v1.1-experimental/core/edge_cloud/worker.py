from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..source_revision import describe_source_revision


SOURCE_REVISION = describe_source_revision(Path(__file__).resolve())


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def host_fingerprint() -> str:
    identity = f"{socket.gethostname()}:{uuid.getnode():012x}".encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


class WorkerState:
    def __init__(self, node_id: str, role: str, token: str, delay_seconds: float, event_log: Path, source_revision: dict):
        if not node_id or role not in {"cloud", "edge"}:
            raise ValueError("node_id is required and role must be cloud or edge")
        if delay_seconds < 0 or delay_seconds > 30:
            raise ValueError("delay_seconds must be between 0 and 30")
        self.node_id = node_id
        self.role = role
        self.token = token
        self.delay_seconds = delay_seconds
        self.event_log = event_log
        self.source_revision = source_revision
        self.lock = threading.Lock()

    def emit(self, event: str, **payload: Any) -> None:
        record = {
            "time": utc_now(),
            "event": event,
            "node_id": self.node_id,
            "node_role": self.role,
            "host": socket.gethostname(),
            "host_fingerprint": host_fingerprint(),
            "pid": os.getpid(),
            "source_revision": self.source_revision,
            **payload,
        }
        self.event_log.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, self.event_log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())


def make_handler(state: WorkerState):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AlternativeFrameWorker/1.0"

        def log_message(self, _format, *_args):
            pass

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path != "/health":
                return self._send(404, {"error": "not found"})
            return self._send(200, {
                "node_id": state.node_id,
                "role": state.role,
                "host": socket.gethostname(),
                "host_fingerprint": host_fingerprint(),
                "source_revision": state.source_revision,
                "status": "ready",
                "time": utc_now(),
            })

        def do_POST(self):
            if urlparse(self.path).path != "/execute":
                return self._send(404, {"error": "not found"})
            supplied = self.headers.get("X-AF-Token", "")
            if not hmac.compare_digest(supplied, state.token):
                return self._send(401, {"error": "unauthorized"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 65536:
                    return self._send(413, {"error": "request body size is invalid"})
                request = json.loads(self.rfile.read(length))
                run_id = str(request["run_id"])
                task_id = str(request["task_id"])
                payload = request["payload"]
                if request.get("operation") != "digest" or not isinstance(payload, dict):
                    return self._send(400, {"error": "unsupported operation"})
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                return self._send(400, {"error": f"invalid request: {type(exc).__name__}"})

            state.emit("worker_task_started", run_id=run_id, task_id=task_id)
            if state.delay_seconds:
                time.sleep(state.delay_seconds)
            encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            result = {
                "run_id": run_id,
                "task_id": task_id,
                "node_id": state.node_id,
                "node_role": state.role,
                "host": socket.gethostname(),
                "host_fingerprint": host_fingerprint(),
                "source_revision": state.source_revision,
                "digest": hashlib.sha256(encoded).hexdigest(),
                "payload_size_bytes": len(encoded),
            }
            state.emit("worker_task_finished", run_id=run_id, task_id=task_id, digest=result["digest"])
            return self._send(200, {"success": True, "result": result})

    return Handler


def serve(host: str, port: int, node_id: str, role: str, token: str, delay_seconds: float, event_log: Path):
    state = WorkerState(node_id, role, token, delay_seconds, event_log, SOURCE_REVISION)
    server = ThreadingHTTPServer((host, port), make_handler(state))
    server.daemon_threads = True
    state.emit("worker_started", bind_host=host, port=server.server_address[1], pid=os.getpid())
    print(json.dumps({"event": "worker_ready", "node_id": node_id, "host": socket.gethostname(), "port": server.server_address[1]}), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        state.emit("worker_stopped", pid=os.getpid())


def main(argv=None):
    parser = argparse.ArgumentParser(description="Alternative-Frame allowlisted remote worker")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--role", choices=("cloud", "edge"), required=True)
    parser.add_argument("--token", default=os.environ.get("AF_EDGE_CLOUD_TOKEN", ""))
    parser.add_argument("--delay-seconds", type=float, default=0)
    parser.add_argument("--event-log", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("set AF_EDGE_CLOUD_TOKEN or pass --token")
    serve(args.host, args.port, args.node_id, args.role, args.token, args.delay_seconds, args.event_log)


if __name__ == "__main__":
    main()
