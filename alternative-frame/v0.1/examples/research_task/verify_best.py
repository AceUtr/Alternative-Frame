"""Independently rerun the selected configuration from best_config.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_baseline import run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/dataset.json")
    parser.add_argument("--config", default="artifacts/best_config.json")
    parser.add_argument("--output", default="artifacts/verification_metrics.json")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    features = tuple(config["features_used"])
    if not features or not all(item in {"x1", "x2"} for item in features):
        raise ValueError("best config contains unsupported features")
    metrics = run(
        Path(args.dataset),
        Path(args.output),
        features=features,
        experiment_name=f"verification:{config['best_experiment']}",
    )
    metrics["verified_experiment"] = config["best_experiment"]
    metrics["source_best_score"] = config["best_score"]
    Path(args.output).write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"accuracy={metrics['accuracy']:.6f}")
    print(f"verified_score={metrics['source_best_score']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
