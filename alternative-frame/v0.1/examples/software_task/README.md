# Software Engineering Demo

This deterministic, offline fixture starts with a real failing test. The
Alternative-Frame harness diagnoses it in phase 1, then repairs the Python AST,
runs the exact contracted pytest command, and writes an evidence-backed report
in phase 2.

Run it from `alternative-frame/v0.1`:

```powershell
python run_software_demo.py
```

The entry point creates and resets an isolated workspace below
`runs/software-workspaces/<run_id>/`, so stale repaired code and reports cannot
make a new run pass. This directory remains the human-readable source fixture.
