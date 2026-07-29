"""Generate the fixed offline classification dataset used by the research demo."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


SEED = 1729
TRAIN_ROWS = 160
TEST_ROWS = 40
DATASET_VERSION = "synthetic-centroids-v2"


def _make_row(rng: random.Random, index: int) -> dict[str, object]:
    label = index % 2
    direction = -1.0 if label == 0 else 1.0
    return {
        "id": index,
        # x1 is intentionally a modest baseline feature. x2 is retained for a
        # later, genuinely improved configuration after interface review.
        "x1": round(rng.gauss(direction * 1.0, 1.1), 8),
        "x2": round(rng.gauss(direction * 0.8, 0.95), 8),
        "label": label,
    }


def generate(output_path: Path) -> dict[str, object]:
    rng = random.Random(SEED)
    rows = [_make_row(rng, index) for index in range(TRAIN_ROWS + TEST_ROWS)]
    rng.shuffle(rows)
    payload = {
        "metadata": {
            "dataset_version": DATASET_VERSION,
            "seed": SEED,
            "split": {"train_rows": TRAIN_ROWS, "test_rows": TEST_ROWS},
            "features": ["x1", "x2"],
            "target": "label",
        },
        "train": rows[:TRAIN_ROWS],
        "test": rows[TRAIN_ROWS:],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/dataset.json")
    args = parser.parse_args()
    payload = generate(Path(args.output))
    print(f"dataset_rows={len(payload['train']) + len(payload['test'])}")
    print(f"seed={SEED}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
