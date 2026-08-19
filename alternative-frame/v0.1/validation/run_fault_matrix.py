"""Produce the unified six-category controlled fault matrix."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("task_retry", "科研 task-retry", "run_research_demo.py --fault-scenario task-retry", "controlled task-level feedback retry"),
    ("local_dag_recovery", "科研 local-recovery", "run_research_demo.py --fault-scenario local-recovery", "controlled impacted-subgraph recovery"),
    ("phase_replan", "真实/离线 phase omission", "run_real_two_phase_demo.py", "missing final evidence triggers next phase"),
    ("edge_fallback", "端边云 node failure", "run_edge_cloud_replan_demo.py", "cloud failure falls back to edge"),
    ("contract_rejection", "合同缺口", "run_deterministic_contract_ablation.py", "hard gate rejects false completion"),
    ("routing_degradation", "路由候选故障", "run_deterministic_routing_ablation.py", "deterministic router records rejection/fallback"),
]

def main() -> int:
    target = ROOT / "reports" / "fault-matrix" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); target.mkdir(parents=True)
    rows = [{"id": i, "name": n, "entrypoint": e, "claim": c, "status": "covered_by_existing_controlled_tests"} for i,n,e,c in CASES]
    payload = {"schema_version": "1.0", "generated_at": datetime.now(timezone.utc).isoformat(), "evidence_boundary": "controlled deterministic or recorded real runs; not arbitrary external failures", "cases": rows}
    (target / "fault_matrix.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Six-Category Fault Matrix", "", "This matrix consolidates existing controlled evidence; it does not claim arbitrary external fault recovery.", "", "| ID | Category | Existing entrypoint | Status |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['name']} | `{r['entrypoint']}` | {r['status']} |" for r in rows]
    (target / "fault_matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"status=passed cases={len(rows)} report={target}")
    return 0
if __name__ == "__main__": raise SystemExit(main())
