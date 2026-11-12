from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def describe_source_revision(start: str | Path) -> dict[str, Any]:
    try:
        start_path = Path(start).resolve()
        working_directory = start_path.parent if start_path.is_file() else start_path
        repo_root = Path(subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=working_directory, capture_output=True, text=True, check=True,
        ).stdout.strip())
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-c", "core.quotepath=false", "status", "--porcelain", "--untracked-files=all", "--no-renames"],
            cwd=repo_root, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        dirty_files = []
        for line in status:
            if len(line) < 4:
                continue
            relative = line[3:]
            path = repo_root / relative
            item = {"path": relative.replace("\\", "/"), "status": line[:2]}
            if path.is_file():
                item["sha256"] = sha256_file(path)
            else:
                item["sha256"] = None
            dirty_files.append(item)
        dirty_files.sort(key=lambda item: item["path"])
        tree_hash = hashlib.sha256(
            json.dumps(dirty_files, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {
            "branch": branch,
            "commit": commit,
            "working_tree_clean": not status,
            "working_tree_sha256": tree_hash,
            "dirty_files": dirty_files,
        }
    except (OSError, subprocess.CalledProcessError):
        empty_hash = hashlib.sha256(b"[]").hexdigest()
        return {
            "branch": "unknown",
            "commit": "unknown",
            "working_tree_clean": False,
            "working_tree_sha256": empty_hash,
            "dirty_files": [],
        }
