# Final Evidence

## Software Engineering Demo

This branch contains the offline deterministic software engineering Demo v1.0
closure. The frozen fixture uses the flat paths:

- `examples/software_task/app.py`
- `examples/software_task/test_app.py`

The executable entry point is:

```powershell
python run_software_demo.py --fault-scenario none
python run_software_demo.py --fault-scenario retry-once
python run_software_demo.py --fault-scenario local-recovery
```

Each successful run prints:

```text
Status: completed
Phase count: <positive integer>
Runtime root: <existing path>
```

Each runtime root contains:

```text
state.json
events.jsonl
workspace/artifacts/software_report.md
workspace/artifacts/code_diff.patch
workspace/artifacts/test_log.txt
```

The exact regression command remains:

```powershell
python -m pytest test_app.py -q -p no:cacheprovider
```

## Validation Commands

Run these from `alternative-frame/v0.1` before requesting freeze:

```powershell
python validate_contribution.py --domain software
python -m pytest tests/test_software_demo.py -q -p no:cacheprovider
python -m pytest -q -p no:cacheprovider
python run_software_demo.py --fault-scenario none
python run_software_demo.py --fault-scenario retry-once
python run_software_demo.py --fault-scenario local-recovery
git diff --check
git status --short --branch
```

## Expected Evidence

- Contribution gate: `status=passed`.
- Software tests: all tests pass.
- Full regression: all tests pass.
- `none`: completes in two phases and writes current-run report evidence.
- `retry-once`: completes with `implement_fix attempts=2` and structured
  `retry_feedback` in `AgentResult.tool_records` and `events.jsonl`.
- `local-recovery`: completes with frozen predecessor nodes and rerun impacted
  nodes recorded in `events.jsonl`.
- `git diff --check`: no whitespace errors.
- `git status --short --branch`: clean after generated validation reports are
  ignored or removed.

## Known Limits

- The software Demo uses deterministic local agents for offline reproducibility.
- Real OpenAI-compatible model execution is intentionally left for the unified
  integration branch.
