"""Offline hypothesis/selection/protocol primitives for the research fixture.

Workflow adaptation of GenExp and Robin; no upstream implementation is copied.
Ranking is a transparent round-robin comparison of training-only cross-validation
scores, not an implementation of Robin's LLM judge or Bradley-Terry model.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from copy import deepcopy
from typing import Any, Callable

from examples.research_task.run_baseline import _fit_centroids, _predict


REQUIRED_FIELDS = ("id", "source", "status", "created_by", "metadata")
FEATURE_SETS = (("x1",), ("x1", "x2"))


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def artifact(kind: str, status: str, metadata: dict, **content) -> dict:
    return {
        "id": f"{kind}-{digest([metadata, content])[:16]}",
        "source": "offline-research-fixture",
        "status": status,
        "created_by": f"research.{kind}.v1",
        "metadata": deepcopy(metadata),
        **content,
    }


def validate_record(record: dict) -> None:
    if not isinstance(record, dict) or any(not record.get(k) for k in REQUIRED_FIELDS):
        raise ValueError("research record requires id/source/status/created_by/metadata")
    if any(not isinstance(record[k], str) for k in ("id", "source", "status", "created_by")):
        raise ValueError("research record identity, source, status and creator must be strings")
    if not isinstance(record["metadata"], dict):
        raise ValueError("research record metadata must be an object")


class CandidateEvaluationError(ValueError):
    """Typed failure with an inspectable result and no fabricated ranking."""

    def __init__(self, reason: str, metadata: dict | None = None):
        super().__init__(reason)
        self.result = artifact(
            "candidate-ranking", "failed", metadata or {"method": "offline-cv-v1"},
            rankings=[], pairwise_comparisons=[], selected_id=None,
            error={"category": "candidate_evaluation_failed", "message": reason},
        )


def generate_hypotheses(context: dict) -> list[dict]:
    """Generate two testable, comparable feature hypotheses without model APIs."""
    seed = context.get("seed", 1729)
    if type(seed) is not int:
        raise ValueError("seed must be an integer")
    version = context.get("dataset_version")
    if not isinstance(version, str) or not version:
        raise ValueError("dataset_version must be a non-empty string")
    candidates = []
    for features in FEATURE_SETS:
        candidates.append(artifact(
            "hypothesis", "candidate",
            {"seed": seed, "dataset_version": version, "features_used": list(features)},
            statement=(
                "A nearest-centroid classifier using " + ", ".join(features)
                + " can be evaluated reproducibly on the fixed classification task."
            ),
            prediction=("Adding x2 improves generalization over the x1 reference."
                        if len(features) > 1 else "x1 provides the reference accuracy."),
        ))
    random.Random(seed).shuffle(candidates)
    return candidates


def _folds(evidence: dict) -> list[tuple[list[dict], list[dict]]]:
    seed = evidence.get("seed")
    if type(seed) is not int:
        raise ValueError("evaluation seed must be an integer")
    rows = evidence.get("train")
    if not isinstance(rows, list) or not rows:
        raise ValueError("training evidence must be a non-empty list")
    groups: dict[int, list[dict]] = {0: [], 1: []}
    identifiers = set()
    for row in rows:
        if not isinstance(row, dict) or type(row.get("id")) is not int:
            raise ValueError("training rows require integer IDs")
        if row["id"] in identifiers:
            raise ValueError("training IDs must be unique")
        identifiers.add(row["id"])
        if type(row.get("label")) is not int or row["label"] not in groups:
            raise ValueError("training labels must be 0 or 1")
        for feature in ("x1", "x2"):
            value = row.get(feature)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                raise ValueError("training features must be finite numbers")
        groups[row["label"]].append(row)
    if any(len(group) < 5 for group in groups.values()):
        raise ValueError("five-fold evaluation requires at least five rows per label")
    buckets: list[list[dict]] = [[] for _ in range(5)]
    rng = random.Random(seed)
    for label in sorted(groups):
        group = sorted(groups[label], key=lambda row: row["id"])
        rng.shuffle(group)
        for index, row in enumerate(group):
            buckets[index % 5].append(row)
    return [([r for j, bucket in enumerate(buckets) if j != i for r in bucket], test)
            for i, test in enumerate(buckets)]


def evaluate_candidate(candidate: dict, evidence: dict) -> dict:
    """Independent evaluation reuses the fixture's actual classifier routines."""
    features = tuple(candidate["metadata"]["features_used"])
    fold_scores = []
    for train, validation in _folds(evidence):
        centroids = _fit_centroids(train, features)
        fold_scores.append(sum(
            _predict(row, centroids, features) == row["label"] for row in validation
        ) / len(validation))
    score = sum(fold_scores) / len(fold_scores)
    return {"cv_accuracy": score, "fold_accuracies": fold_scores,
            "feature_count": len(features)}


def rank_candidates(
    candidates: list[dict], evidence: dict | None = None,
    *, evaluator: Callable[[dict, dict], dict] | None = None,
) -> list[dict]:
    """Return scored candidates or raise a typed, structured evaluation failure.

    The evaluator receives no other candidate, ordinal, or prior score. Pairwise
    comparisons prefer higher CV accuracy, then fewer features; exact ties use
    a stable ID only for presentation. All validation uses training rows only.
    """
    metadata = {"method": "training-cv-round-robin-v1"}
    try:
        if not isinstance(evidence, dict):
            raise ValueError("training evidence is required")
        if len(candidates) < 2:
            raise ValueError("at least two candidates are required")
        _folds(evidence)
        metadata.update({"seed": evidence["seed"],
                         "training_sha256": digest(evidence["train"]),
                         "dataset_version": evidence["dataset_version"]})
        ids = set()
        evaluated = []
        for candidate in sorted(candidates, key=lambda c: c["id"]):
            validate_record(candidate)
            if candidate["id"] in ids:
                raise ValueError("candidate IDs must be unique")
            ids.add(candidate["id"])
            features = candidate["metadata"].get("features_used", [])
            if tuple(features) not in FEATURE_SETS:
                raise ValueError("unsupported fixture feature configuration")
            if (candidate["metadata"].get("seed") != evidence["seed"]
                    or candidate["metadata"].get("dataset_version") != evidence["dataset_version"]):
                raise ValueError("candidate and evaluation provenance differ")
            scores = (evaluator or evaluate_candidate)(deepcopy(candidate), deepcopy(evidence))
            value = scores["cv_accuracy"]
            folds = scores["fold_accuracies"]
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not 0 <= value <= 1):
                raise ValueError("candidate score must be finite and within [0, 1]")
            if (not isinstance(folds, list) or len(folds) != 5
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           or not 0 <= v <= 1 for v in folds)
                    or abs(sum(folds) / 5 - value) > 1e-12
                    or type(scores["feature_count"]) is not int
                    or scores["feature_count"] != len(features)):
                raise ValueError("candidate score has inconsistent fold evidence")
            row = deepcopy(candidate)
            row["status"] = "ranked"
            row["created_by"] = "research.independent_cv_evaluator.v1"
            row["metadata"].update({**metadata, "scores": scores,
                                    "total_score": value, "pairwise_wins": 0,
                                    "evaluation_basis": "Five stratified folds of training data; held-out test data excluded.",
                                    "comparisons": []})
            evaluated.append(row)
        for left, right in itertools.combinations(evaluated, 2):
            lkey = (left["metadata"]["total_score"], -left["metadata"]["scores"]["feature_count"])
            rkey = (right["metadata"]["total_score"], -right["metadata"]["scores"]["feature_count"])
            winner = left if lkey > rkey else right if rkey > lkey else None
            comparison = {
                "pair": [left["id"], right["id"]],
                "winner_id": winner["id"] if winner else None,
                "reason": "Higher training CV accuracy; equal accuracy prefers fewer features; otherwise a tie.",
                "scores": {r["id"]: r["metadata"]["total_score"] for r in (left, right)},
            }
            for row in (left, right):
                row["metadata"]["comparisons"].append(deepcopy(comparison))
            if winner:
                winner["metadata"]["pairwise_wins"] += 1
        evaluated.sort(key=lambda r: (-r["metadata"]["pairwise_wins"],
                                     -r["metadata"]["total_score"],
                                     r["metadata"]["scores"]["feature_count"], r["id"]))
        for rank, row in enumerate(evaluated, 1):
            row["metadata"]["rank"] = rank
        return evaluated
    except Exception as exc:
        raise CandidateEvaluationError(str(exc), metadata) from exc


def build_protocol(hypothesis: dict) -> dict:
    validate_record(hypothesis)
    if (hypothesis["status"] != "ranked" or type(hypothesis["metadata"].get("rank")) is not int
            or hypothesis["metadata"]["rank"] != 1):
        raise ValueError("protocol requires the selected, successfully ranked hypothesis")
    features = hypothesis["metadata"]["features_used"]
    if tuple(features) not in FEATURE_SETS:
        raise ValueError("unsupported protocol feature configuration")
    return artifact(
        "protocol", "ready", hypothesis["metadata"],
        hypothesis_id=hypothesis["id"],
        question="Does adding x2 improve held-out nearest-centroid accuracy?",
        intervention={"features_used": features},
        control={"features_used": ["x1"], "experiment": "nearest_centroid_v1"},
        measurement={"metric": "accuracy", "direction": "max", "split": "held-out-test"},
        steps=["Use the fixed dataset and split.",
               "Run the reference and two-feature experiments with existing tools.",
               "Compare measured metrics separately from training CV priorities.",
               "Rerun the observed best configuration and check tolerance 1e-9."],
        constraints={"offline": True, "third_party_runtime_dependencies": [],
                     "selection_uses_test_data": False},
        execution={
            "dataset_path": "data/dataset.json",
            "seed": hypothesis["metadata"]["seed"],
            "reference_command": "python run_baseline.py --dataset data/dataset.json --output artifacts/baseline_metrics.json",
            "comparison_command": "python run_improved.py --dataset data/dataset.json --output artifacts/improved_metrics.json",
            "verification_command": "python verify_best.py --dataset data/dataset.json --config artifacts/best_config.json --output artifacts/verification_metrics.json --tolerance 0.000000001",
            "selection_policy": "CV chooses the priority hypothesis; observed metrics choose the configuration to verify.",
        },
        expected_outputs=["artifacts/baseline_metrics.json", "artifacts/improved_metrics.json",
                          "artifacts/best_config.json", "artifacts/verification_metrics.json"],
    )
