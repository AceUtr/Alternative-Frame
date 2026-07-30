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

Delete `data/dataset.json` and `artifacts/` to reset. Re-running the commands
recreates identical inputs and metrics.
