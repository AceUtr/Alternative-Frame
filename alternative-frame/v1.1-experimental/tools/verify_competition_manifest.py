"""Verify a generated competition evidence package without rerunning experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    package = manifest_path.parent
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = []
    entries = payload.get("sources", []) + payload.get("charts", []) + payload.get("validations", []) + payload.get("configurations", []) + payload.get("documents", [])
    for entry in entries:
        path = package / entry["path"]
        if not path.is_file():
            errors.append(f"missing: {entry['path']}")
            continue
        actual = sha256(path)
        if actual != entry.get("sha256"):
            errors.append(f"hash mismatch: {entry['path']}")
    if payload.get("live_api_status") == "pending_credentials" and payload.get("api_runs"):
        errors.append("pending_credentials package cannot contain api_runs")
    if errors:
        for error in errors:
            print(f"[FAIL] {error}")
        return 1
    print(f"[PASS] {len(payload.get('sources', []))} sources and {len(payload.get('charts', []))} charts verified")
    print(f"candidate_commit={payload.get('candidate_commit')}")
    print(f"evidence_commit={payload.get('evidence_commit')}")
    print(f"live_api_status={payload.get('live_api_status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
