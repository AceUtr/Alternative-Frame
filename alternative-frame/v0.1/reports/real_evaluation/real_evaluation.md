# Real Research Evaluation

Evidence type: `recorded_real_run`.

This report is generated from real previously recorded research-demo runs. It is not a live competition rerun.

Source summary: `benchmarks/results/summary/research_recorded-20260814T045729288642Z.json`

## Results

| Case | Goal | Completed tasks | Cumulative planned tasks | First pass | Local recovery | Extra tasks | Phases | Phase-1 contract | Final contract |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| research_normal | PASS | 8 | 8 | 8 | 0 | 0 | 2 | FAIL | PASS |
| research_local_recovery | PASS | 8 | 11 | 7 | 1 | 3 | 2 | FAIL | PASS |

## Interpretation

- Both recorded runs eventually completed the final research goal.
- The normal run completed 8 tasks with 0 local recovery cycles.
- The recovery run completed 8 final tasks, triggered 1 local recovery cycle, and accumulated 3 extra planned tasks.
- First-pass successful task count changed from 8 to 7.
- Phase 1 did not satisfy the final contract in either recorded run; phase 2 completed the missing verification work and reached final acceptance.

## Metric caveats

- `cumulative_planned_tasks` includes tasks introduced by recovery. Therefore `8 / 11` must not be presented as a 72.7% final goal success rate.
- Missing model token usage and model cost are `unknown`, not zero.
- Device/edge/cloud routing was not recorded in these historical samples and must not be inferred.
- This dataset demonstrates actual recovery and contract behavior, but it is not yet a controlled `recovery disabled vs enabled` experiment.

## Next controlled experiments

1. Recovery disabled vs three-level recovery.
2. Contract validation disabled vs enabled.
3. Single-agent vs multi-agent execution.
4. Fixed node placement vs dynamic device/edge/cloud routing.
