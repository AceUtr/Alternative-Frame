# Offline research fixture

This fixture uses only Python 3.10+ standard-library modules.

- Dataset version: `synthetic-centroids-v2`
- Random seed: `1729`
- Split: 160 training rows and 40 test rows
- Baseline: nearest-centroid classifier fitted from the training split using
  only the basic feature `x1`
- Primary metric: test-set accuracy (higher is better)

The second generated feature is intentionally excluded from the baseline. It
provides legitimate room for the improved configuration without falsifying or
hard-coding either result. The improved experiment uses both `x1` and `x2`.

Run from this directory:

```powershell
python generate_dataset.py --output data/dataset.json
python run_baseline.py --dataset data/dataset.json --output artifacts/baseline_metrics.json
python run_improved.py --dataset data/dataset.json --output artifacts/improved_metrics.json
```

The Harness compares the two metric files, writes `best_config.json`, and then
runs `verify_best.py` as an independent command. Verification succeeds only
when the rerun accuracy matches `best_config.best_score` within the explicit
absolute tolerance of `1e-9`; a mismatch exits non-zero. From the `v0.1` directory,
`python run_research_demo.py` executes the complete two-phase flow and writes a
PNG chart plus a Markdown report.

The acceptance contract also requires
`improved_accuracy - baseline_accuracy >= 0.000001`; absolute accuracy
thresholds alone cannot make a tied or regressed candidate pass.

The formal entry point supports deterministic recovery demonstrations:

```powershell
python run_research_demo.py --fault-scenario normal
python run_research_demo.py --fault-scenario task-retry
python run_research_demo.py --fault-scenario local-recovery
```

`task-retry` repairs an incorrect output command and removes its bad artifact
after reading structured retry feedback. `local-recovery` uses the existing
`LocalDAGRecoveryController` to rerun only the failed improved-experiment
subgraph. Both scenarios persist auditable events under `runs/research/`.

## Desktop UI

Run `python ui.py`, select `Research Demo (offline)`, choose one of the three
fault scenarios, and confirm the fixed acceptance contract. This mode is fully
offline and never asks for an API key. Cancelling the contract prevents the
controller and tools from starting.

The UI shows phase/task state, DAG nodes, attempts, tool arguments and exit
codes, hard-gate evidence, retry and local-recovery events, and the final
report path. The active controller is exposed to the existing safe-pause
button.

## Audit files

Each CLI or UI run writes:

```text
runs/research/<run_id>/state.json
runs/research/<run_id>/events.jsonl
```

`state.json` contains phases, task counts, evidence records, missing criteria,
and recovery counters. `events.jsonl` is an append-only timeline containing
task, retry, local recovery, hard-gate, and completion events. These run
histories are temporary evidence and must not be committed.

The fixture reset deletes only declared generated outputs. A locked Windows
file causes a clear reset error; no recursive deletion or workspace escape is
used.

Delete `data/dataset.json` and `artifacts/` to reset. Re-running the commands
recreates identical inputs and metrics.
