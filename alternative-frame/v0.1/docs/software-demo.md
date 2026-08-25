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

From `alternative-frame/v0.1`:

```powershell
python run_software_demo.py
python -m pytest tests/test_software_demo.py -q -p no:cacheprovider
python validate_contribution.py --domain software
```

Expected smoke output includes `status=completed` and `phases=2`. Persistent
state and events are written below `runs/software/<run_id>/`; the resettable
fixture is isolated below `runs/software-workspaces/<run_id>/`.

## Scope

This fixture proves orchestration, real tool execution, evidence provenance,
contract rejection, and cross-phase recovery. It does not claim autonomous
repair of arbitrary repositories or arbitrary external-failure recovery.
