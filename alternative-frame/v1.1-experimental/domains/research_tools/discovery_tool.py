"""Domain tool joining discovery artifacts to existing execution/acceptance."""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.tools import ToolResult
from .dataset_inspector import DatasetInspector
from .discovery import (
    CandidateEvaluationError, artifact, build_protocol, digest,
    generate_hypotheses, rank_candidates, validate_record,
)


DISCOVERY_PATHS = {
    "hypotheses": "artifacts/hypotheses.json",
    "ranking": "artifacts/candidate_rankings.json",
    "protocol": "artifacts/experimental_protocol.json",
    "attempts": "artifacts/candidate_evaluation_attempts.json",
}


class ResearchDiscoveryTool(DatasetInspector):
    """Retain the inspection schema; add independently evaluated domain outputs."""

    name = "research_discovery"

    def __init__(self, workspace: str | Path):
        super().__init__(workspace)
        self.attempts: list[dict] = []
        fault = os.environ.get("RESEARCH_EVALUATION_FAILURES", "0")
        if fault not in {"0", "1", "always"}:
            raise ValueError("RESEARCH_EVALUATION_FAILURES must be 0, 1, or always")
        self.failure_mode = fault

    def _write(self, name: str, value: dict) -> None:
        path = self._resolve(DISCOVERY_PATHS[name])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                   allow_nan=False) + "\n", encoding="utf-8")

    def execute(self, arguments: dict) -> ToolResult:
        # Remove any previous successful protocol/ranking before a fresh attempt.
        try:
            for name in ("ranking", "protocol"):
                path = self._resolve(DISCOVERY_PATHS[name])
                if path.is_file():
                    path.unlink()
        except (OSError, ValueError) as exc:
            return ToolResult(self.name, False, error=f"discovery output preparation failed: {exc}")
        inspection = super().execute(arguments)
        if not inspection.success:
            return inspection
        metadata = {"method": "training-cv-round-robin-v1"}
        try:
            dataset = json.loads(self._resolve(arguments["dataset_path"]).read_text(encoding="utf-8"))
            evidence = {"train": dataset["train"], "seed": dataset["metadata"]["seed"],
                        "dataset_version": dataset["metadata"]["dataset_version"]}
            metadata.update({"seed": evidence["seed"], "dataset_version": evidence["dataset_version"],
                             "training_sha256": digest(evidence["train"])})
            hypotheses = generate_hypotheses(evidence)
            self._write("hypotheses", artifact("hypotheses", "generated", metadata,
                                               candidates=hypotheses))
            if self.failure_mode == "always" or (self.failure_mode == "1" and not self.attempts):
                raise CandidateEvaluationError("Controlled independent evaluator failure", metadata)
            rankings = rank_candidates(hypotheses, evidence)
            comparisons = {tuple(c["pair"]): c for row in rankings
                           for c in row["metadata"]["comparisons"]}
            ranking = artifact("candidate-ranking", "ranked", metadata,
                               rankings=rankings, selected_id=rankings[0]["id"],
                               pairwise_comparisons=list(comparisons.values()))
            protocol = build_protocol(rankings[0])
            self._write("ranking", ranking)
            self._write("protocol", protocol)
            self.attempts.append(artifact("evaluation-attempt", "success", metadata,
                                         attempt=len(self.attempts) + 1,
                                         selected_id=ranking["selected_id"]))
            self._write("attempts", artifact("evaluation-attempts", "success", metadata,
                                             attempts=self.attempts))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            failure = (exc.result if isinstance(exc, CandidateEvaluationError)
                       else CandidateEvaluationError(str(exc), metadata).result)
            self.attempts.append(artifact("evaluation-attempt", "failed", metadata,
                                         attempt=len(self.attempts) + 1, failure=failure))
            self._write("ranking", failure)
            self._write("attempts", artifact("evaluation-attempts", "failed", metadata,
                                             attempts=self.attempts))
            return ToolResult(self.name, False, error=str(exc), metadata={
                "evaluation_failure": failure,
                "artifacts": [DISCOVERY_PATHS["ranking"], DISCOVERY_PATHS["attempts"]],
            })
        inspection.tool = self.name
        inspection.output += f"; candidates={len(rankings)}; selected={rankings[0]['id']}"
        inspection.metadata["artifacts"] += list(DISCOVERY_PATHS.values())
        inspection.metadata["discovery"] = {"candidate_count": len(rankings),
                                           "selected_id": rankings[0]["id"]}
        return inspection


def discovery_report(workspace: Path) -> str:
    """Validate current discovery content before an existing report can succeed."""
    docs = {name: json.loads((workspace / path).read_text(encoding="utf-8"))
            for name, path in DISCOVERY_PATHS.items()}
    for doc in docs.values():
        validate_record(doc)
    hypotheses, ranking, protocol = (docs["hypotheses"], docs["ranking"], docs["protocol"])
    dataset = json.loads((workspace / "data/dataset.json").read_text(encoding="utf-8"))
    evidence = {"train": dataset["train"], "seed": dataset["metadata"]["seed"],
                "dataset_version": dataset["metadata"]["dataset_version"]}
    if (hypotheses["status"] != "generated"
            or hypotheses["candidates"] != generate_hypotheses(evidence)):
        raise ValueError("hypothesis provenance or content differs from the current fixture")
    expected = rank_candidates(hypotheses["candidates"], evidence)
    pairs = {tuple(c["pair"]): c for row in expected for c in row["metadata"]["comparisons"]}
    if (ranking["status"] != "ranked" or ranking["rankings"] != expected
            or ranking["selected_id"] != expected[0]["id"]
            or ranking["pairwise_comparisons"] != list(pairs.values())
            or protocol != build_protocol(expected[0])
            or docs["attempts"]["status"] != "success"):
        raise ValueError("discovery evidence is failed, inconsistent, or tampered")
    rows = "\n".join(
        f"| {r['metadata']['rank']} | {r['id']} | {','.join(r['metadata']['features_used'])} "
        f"| {r['metadata']['total_score']:.6f} | {r['metadata']['pairwise_wins']} |"
        for r in expected
    )
    return (
        "\n## Hypothesis selection and protocol\n\n"
        "Candidates were evaluated independently with five-fold training-only CV. "
        "Round-robin comparisons use CV accuracy, then feature count. "
        "These priority scores are distinct from held-out experiment metrics.\n\n"
        "| Rank | Hypothesis | Features | CV accuracy | Pairwise wins |\n"
        "| ---: | --- | --- | ---: | ---: |\n" + rows + "\n\n"
        f"Selected hypothesis: `{ranking['selected_id']}`.\n\n"
        + "\n".join(f"- [{name}]({Path(path).name})" for name, path in DISCOVERY_PATHS.items())
        + "\n"
    )
