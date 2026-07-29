# Offline research fixture

This fixture uses only Python 3.10+ standard-library modules.

- Dataset version: `synthetic-centroids-v2`
- Random seed: `1729`
- Split: 160 training rows and 40 test rows
- Baseline: nearest-centroid classifier fitted from the training split using
  only the basic feature `x1`
- Primary metric: test-set accuracy (higher is better)

The second generated feature is intentionally excluded from the baseline. It
provides legitimate room for a later improved configuration without falsifying
or hard-coding either result.

Run from this directory:

```powershell
python generate_dataset.py --output data/dataset.json
python run_baseline.py --dataset data/dataset.json --output artifacts/baseline_metrics.json
```

Delete `data/dataset.json` and `artifacts/` to reset. Re-running the commands
recreates identical inputs and metrics.
