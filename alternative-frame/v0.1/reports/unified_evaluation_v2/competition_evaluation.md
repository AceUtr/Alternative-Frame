# Competition Evaluation Report

Generated: 2026-08-14T05:41:33.716751+00:00

## Current evidence

### Single Agent vs Multi Agent

Both deterministic conditions completed 100% of tasks.

- Single Agent mean wall-clock: `0.4048s`
- Multi Agent mean wall-clock: `0.3244s`
- Multi Agent speedup: `1.248x`
- Single Agent parallel overlap: `0.0000s`
- Multi Agent parallel overlap: `0.0803s`

This controlled experiment demonstrates orchestration parallelism and role topology only. It does not establish superior LLM reasoning quality.

### Local Recovery

- Recovery OFF: final workflow failed.
- Recovery ON: final workflow succeeded.
- Local recovery cycles: `1`
- Successful unaffected predecessor was not rerun.

This demonstrates both recoverability and locality of recovery.

### Contract Validation

The exact same green phase report is evaluated in both conditions.

- Contract OFF: declared complete.
- Contract ON: rejected completion.
- Only missing criterion: `final_evidence`.

This demonstrates prevention of false completion.

### Recorded Real Research Runs

Historical real research runs are also available as `recorded_real_run` evidence.

They demonstrate that local recovery and multi-phase contract completion have occurred in actual project executions.

They are observational runs, not controlled treatment-vs-control experiments.

## Evidence boundaries

`deterministic_controlled_run` is mechanism-level controlled evidence.

`recorded_real_run` is genuine historical execution evidence.

`live_real_run` will be generated after model API configuration.

Do not present deterministic timing results as evidence of superior LLM reasoning quality.

Do not present recorded historical runs as randomized controlled comparisons.

## Remaining experiments

- Live LLM recovery OFF vs phase recovery vs full recovery.
- Live LLM Single Agent vs Multi Agent.
- Fixed node placement vs dynamic device/edge/cloud routing.
