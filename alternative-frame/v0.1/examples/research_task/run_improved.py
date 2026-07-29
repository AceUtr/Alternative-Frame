"""Run the deterministic two-feature improved experiment."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_baseline import run


IMPROVED_NAME = "nearest_centroid_two_features_v1"
IMPROVED_FEATURES = ("x1", "x2")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/dataset.json")
    parser.add_argument("--output", default="artifacts/improved_metrics.json")
    args = parser.parse_args()
    metrics = run(
        Path(args.dataset),
        Path(args.output),
        features=IMPROVED_FEATURES,
        experiment_name=IMPROVED_NAME,
    )
    print(f"accuracy={metrics['accuracy']:.6f}")
    print(f"test_rows={metrics['test_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
