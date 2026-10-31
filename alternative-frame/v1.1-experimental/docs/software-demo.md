# Software Demo

The software Demo is a deterministic two-phase long-horizon task. It requires
no network, API key, or GPU and runs on the existing Alternative-Frame Harness.

## Flow

1. Phase 1 reads the requirement, source, and test, then runs the exact pytest
   command and records the expected failing exit code in `artifacts/diagnosis.json`.
2. The global contract gate rejects completion because the repaired source,
   successful command evidence, and report are missing.
3. The recovery plan changes the Python operator through a workspace-scoped AST
   tool, reruns the exact command, and builds `artifacts/software_report.md` from
   the real tool record.
4. The controller marks the run complete only after all four contract criteria
   have current-run provenance.

## Run

From `alternative-frame/v1.1-experimental`:

```powershell
python run_software_demo.py --fault-scenario none
python run_software_demo.py --fault-scenario retry-once
python run_software_demo.py --fault-scenario local-recovery
```

Each run creates an isolated runtime directory containing `state.json`,
`events.jsonl`, `run_manifest.json`, and the key artifacts under
`workspace/artifacts/`. The manifest binds the run ID, scenario, exact test
command, real exit codes, and artifact paths for evaluation.

The `retry-once` scenario records a structured retry event after the first
deliberately incorrect AST repair. The `local-recovery` scenario records the
frozen nodes and impacted subgraph after one injected downstream failure.

## Validation

```powershell
python -m pytest tests/test_software_demo.py -q -p no:cacheprovider
python validate_contribution.py --domain software
python validation/software_smoke.py
```

Generated `reports/` and `runs/` output is for local inspection and must not be
committed.

## Scope

This fixture proves orchestration, real tool execution, evidence provenance,
contract rejection, and cross-phase recovery. It does not claim autonomous
repair of arbitrary repositories or arbitrary external-failure recovery.
