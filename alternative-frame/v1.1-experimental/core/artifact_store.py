"""Publish verified run outputs to a stable, inspectable directory."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def publish_run_artifacts(
    source_root: str | Path,
    domain: str,
    run_id: str,
    relative_paths: Iterable[str],
    output_root: str | Path | None = None,
) -> Path:
    """Copy run outputs and write tamper-evident metadata.

    The source workspace remains the execution area. The published directory is
    a read-oriented delivery view and never counts as evidence by itself.
    """
    source = Path(source_root).resolve()
    root = Path(output_root or os.getenv(
        "ALTERNATIVE_FRAME_OUTPUT_DIR",
        str(PROJECT_ROOT / "runs" / "outputs"),
    )).resolve()
    destination = root / str(domain) / str(run_id)
    destination.mkdir(parents=True, exist_ok=True)

    entries = []
    for raw_path in relative_paths:
        relative = Path(str(raw_path))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"artifact path escapes workspace: {raw_path}")
        source_path = (source / relative).resolve()
        if source_path != source and source not in source_path.parents:
            raise ValueError(f"artifact path escapes workspace: {raw_path}")
        if not source_path.is_file():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        entries.append({
            "path": relative.as_posix(),
            "size": target.stat().st_size,
            "sha256": digest,
            "source": str(source_path),
            "run_id": str(run_id),
        })

    manifest = {
        "schema_version": "1.0",
        "domain": str(domain),
        "run_id": str(run_id),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "source_workspace": str(source),
        "entries": entries,
        "note": "Published copies are for inspection; completion is determined by run evidence and acceptance gates.",
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def publish_run_evidence(run_root: str | Path, destination: str | Path) -> None:
    """Copy durable controller evidence beside the published product files."""
    source = Path(run_root).resolve()
    target = Path(destination).resolve()
    target.mkdir(parents=True, exist_ok=True)
    for name in ("state.json", "events.jsonl"):
        path = source / name
        if path.is_file():
            shutil.copy2(path, target / name)
