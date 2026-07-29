"""Fit and evaluate the deterministic nearest-centroid baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


BASELINE_NAME = "nearest_centroid_v1"
FEATURES = ("x1",)


def _load_dataset(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("train") or not payload.get("test"):
        raise ValueError("dataset must contain non-empty train and test splits")
    return payload


def _fit_centroids(rows: list[dict[str, object]]) -> dict[int, tuple[float, ...]]:
    grouped: dict[int, list[dict[str, object]]] = {0: [], 1: []}
    for row in rows:
        grouped[int(row["label"])].append(row)
    if not all(grouped.values()):
        raise ValueError("training split must contain both labels")
    return {
        label: tuple(
            sum(float(row[feature]) for row in label_rows) / len(label_rows)
            for feature in FEATURES
        )
        for label, label_rows in grouped.items()
    }


def _predict(row: dict[str, object], centroids: dict[int, tuple[float, ...]]) -> int:
    distances = {
        label: sum(
            (float(row[feature]) - centroid[index]) ** 2
            for index, feature in enumerate(FEATURES)
        )
        for label, centroid in centroids.items()
    }
    return min(distances, key=lambda label: (distances[label], label))


def run(dataset_path: Path, output_path: Path) -> dict[str, object]:
    dataset = _load_dataset(dataset_path)
    train = list(dataset["train"])
    test = list(dataset["test"])
    centroids = _fit_centroids(train)
    correct = sum(_predict(row, centroids) == int(row["label"]) for row in test)
    accuracy = correct / len(test)
    metrics = {
        "experiment": BASELINE_NAME,
        "dataset_version": dataset["metadata"]["dataset_version"],
        "seed": dataset["metadata"]["seed"],
        "train_rows": len(train),
        "test_rows": len(test),
        "metric_name": "accuracy",
        "accuracy": round(accuracy, 6),
        "correct": correct,
        "features_used": list(FEATURES),
        "centroids": {
            str(label): [round(value, 8) for value in values]
            for label, values in centroids.items()
        },
        "dependencies": {"python": ">=3.10", "third_party": []},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/dataset.json")
    parser.add_argument("--output", default="artifacts/baseline_metrics.json")
    args = parser.parse_args()
    metrics = run(Path(args.dataset), Path(args.output))
    print(f"accuracy={metrics['accuracy']:.6f}")
    print(f"test_rows={metrics['test_rows']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
