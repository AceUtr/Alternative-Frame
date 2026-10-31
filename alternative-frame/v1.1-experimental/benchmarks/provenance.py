from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path


def benchmark_provenance(run_id: str, config_path: str, command: str, root: Path) -> dict:
    config = Path(config_path)
    if not config.is_absolute():
        config = (Path.cwd() / config).resolve()
    config_hash = None
    if config.is_file():
        config_hash = hashlib.sha256(config.read_bytes()).hexdigest()
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        commit = "unknown"
    tag = os.getenv("CANDIDATE_TAG")
    if not tag:
        try:
            tag = subprocess.run(
                ["git", "describe", "--exact-match", "--tags", "HEAD"], cwd=root,
                check=True, capture_output=True, text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            tag = None
    return {
        "run_id": run_id,
        "candidate_tag": tag,
        "candidate_commit": commit,
        "command": command,
        "config_path": str(config.relative_to(root)) if config.is_relative_to(root) else config.name,
        "config_sha256": config_hash,
    }
