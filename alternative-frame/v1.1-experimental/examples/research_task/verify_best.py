"""Independently rerun the selected configuration from best_config.json."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from run_baseline import run


DEFAULT_TOLERANCE = 1e-9


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/dataset.json")
    parser.add_argument("--config", default="artifacts/best_config.json")
    parser.add_argument("--output", default="artifacts/verification_metrics.json")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    args = parser.parse_args()
    if not math.isfinite(args.tolerance) or args.tolerance < 0:
        raise ValueError("tolerance must be a finite non-negative number")
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    features = tuple(config["features_used"])
    if not features or not all(item in {"x1", "x2"} for item in features):
        raise ValueError("best config contains unsupported features")
    expected_score = float(config["best_score"])
    if not math.isfinite(expected_score):
        raise ValueError("best_score must be finite")
    metrics = run(
        Path(args.dataset),
        Path(args.output),
        features=features,
        experiment_name=f"verification:{config['best_experiment']}",
    )
    actual_score = float(metrics["accuracy"])
    score_delta = abs(actual_score - expected_score)
    verification_passed = score_delta <= args.tolerance
    metrics["verified_experiment"] = config["best_experiment"]
    metrics["source_best_score"] = expected_score
    metrics["verification_tolerance"] = args.tolerance
    metrics["verification_delta"] = score_delta
    metrics["verification_passed"] = verification_passed
    Path(args.output).write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"accuracy={actual_score:.6f}")
    print(f"verified_score={expected_score:.6f}")
    print(f"verification_delta={score_delta:.12f}")
    if not verification_passed:
        print(
            "verification failed: "
            f"actual accuracy {actual_score:.12f} differs from "
            f"best_score {expected_score:.12f} by {score_delta:.12f}, "
            f"exceeding tolerance {args.tolerance:.12f}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
