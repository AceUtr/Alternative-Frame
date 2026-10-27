# Edge-Cloud Demo Fixture

This directory is reserved for deterministic task inputs used by the local
device/edge/cloud simulator.  The current smoke demo uses in-memory actions so
that it remains fast, offline, and reproducible.

Run from `alternative-frame/v0.1`:

```powershell
python run_edge_cloud_demo.py
```

Fixed run samples for evaluation are in `samples/`:

- `normal/`: normal node routing.
- `cloud_edge_fallback/`: cloud execution fails and the task falls back to edge.
- `pause_resume/`: the run pauses after phase 2; after resume, a current probe
  finds cloud offline and routes the remaining task to edge.

Each sample contains `state.json`, `events.jsonl`, and `runtime_view.json` with
the same `run_id`. Reproduce the offline-after-resume case from this directory
with:

```powershell
python -c "from pathlib import Path; from run_edge_cloud_replan_demo import run_demo; run_demo(Path('runs/edge_cloud_replan'), 'pause_resume_repro', resume_cloud_online=False)"
```
