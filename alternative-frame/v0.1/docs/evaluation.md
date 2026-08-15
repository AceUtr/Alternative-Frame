# Evaluation Methodology

## 1. Purpose

The evaluation layer measures whether Alternative-Frame improves
execution reliability, recovery behavior, contract correctness,
and orchestration efficiency.

Evaluation evidence is deliberately separated by evidence class.
Results from different evidence classes must not be silently mixed.

## 2. Evidence Classes

### deterministic_controlled_run

A controlled experiment with deterministic task behavior.

Used for:

- Single Agent vs Multi Agent orchestration topology.
- Recovery OFF vs local recovery ON.
- Contract validation OFF vs ON.

These runs are suitable for mechanism-level claims because the
input, task behavior, and injected failures are controlled.

They are not evidence of superior LLM reasoning quality.

### recorded_real_run

Historical runs produced by the actual research-demo execution
pipeline.

These runs demonstrate that project mechanisms such as local
recovery and multi-phase contract completion have occurred in
real project execution.

They are observational evidence and must not be presented as
controlled treatment-vs-control experiments.

### live_real_run

Live model-driven benchmark runs.

These require an API model and will be added separately.

No live-model claim should be made until those experiments have
actually been executed.

## 3. Core Metrics

The evaluation schema records:

- Final goal completion.
- Task count.
- Successful tasks.
- Failed tasks.
- First-pass success count.
- Retry count.
- Local recovery count.
- Phase count.
- Additional phase count.
- Wall-clock duration.
- Model-call count.
- Prompt tokens.
- Completion tokens.
- Total tokens.
- Estimated cost.
- Tool-call count.
- Successful tool calls.
- Human interventions.
- Device task count.
- Edge task count.
- Cloud task count.
- Unknown-node task count.
- Per-node failure counts.
- Per-node duration.

## 4. Unknown Values

Missing observations must not be converted into numeric zero.

For example:

- no token telemetry -> token count is unknown;
- no model pricing -> estimated cost is unknown;
- no routing evidence -> node placement is unknown.

Zero means a value was observed and measured as zero.

Unknown means the value was not available.

## 5. Controlled Experiments

### 5.1 Single Agent vs Multi Agent

Current deterministic evidence compares:

- one serialized universal backend;
- multiple role-specific backends.

Both conditions use the same DAG, task implementation,
success criteria, Orchestrator, and parallel scheduling policy.

Current evidence establishes orchestration parallelism benefit,
not superior language-model reasoning quality.

### 5.2 Recovery OFF vs Recovery ON

A deterministic failure is injected into the `compute` node of:

`prepare -> compute -> verify`

With recovery disabled, the workflow remains failed.

With local recovery enabled:

- the failed node is identified;
- the blocked downstream node is identified;
- the successful predecessor is frozen;
- only the impacted subgraph is rerun.

The experiment therefore measures both recoverability and
recovery locality.

### 5.3 Contract Validation OFF vs ON

Both conditions receive the same successful phase report.

The workspace contains:

- `calculator.py`;
- provenance for `calculator.py`;
- exact successful test-command evidence.

`FINAL_EVIDENCE.md` is deliberately missing.

Without the contract gate, the successful phase is declared
complete.

With the contract gate, completion is rejected because the
`final_evidence` criterion is missing.

This demonstrates prevention of false completion.

### 5.4 Fixed vs Dynamic Device/Edge/Cloud Routing

Pending integration with the routing interface owned by the
routing module.

No routing-performance claim should be made until the routing
policy and node-placement evidence are available.

## 6. Recorded Research Evidence

Two real recorded research runs are currently available.

They demonstrate:

- final goal completion;
- multi-phase execution;
- contract completion after additional work;
- a real local-recovery event in the recovery sample.

The recovery sample contains cumulative planning work introduced
by recovery.

Therefore `8 / 11` must not be interpreted as a 72.7% final-goal
completion rate.

## 7. Reproducibility

Benchmark outputs are stored separately from benchmark source code.

Generated run outputs must not overwrite previous raw evidence.

Each benchmark run should use:

- a unique run ID;
- an isolated workspace;
- append-only raw results;
- separately generated summaries.

## 8. Current Validation Status

D evaluation tests currently cover:

- metric extraction;
- real recorded samples;
- benchmark execution;
- evaluation reports;
- recovery modes;
- deterministic recovery ablation;
- deterministic contract ablation;
- unified evaluation;
- deterministic agent-topology ablation;
- UI evaluation views.

Live LLM and device/edge/cloud experiments remain pending.

## 9. Fixed Cloud vs Dynamic Device/Edge/Cloud Routing

Status: PASS — deterministic controlled evidence.

The C runtime is integrated through the real:

- `NodeRouter`
- `TaskRequirements`
- `RuntimeExecutor`
- `DeviceNode`
- `EdgeNode`
- `CloudNode`

Controlled workload:

A compute task prefers Cloud and an execution-time Cloud outage is
injected.

### Fixed Cloud

- Cloud is the only execution target.
- The Cloud attempt fails.
- No fallback is available.
- Final completion is false.

### Dynamic Routing

- Cloud is selected first.
- The failed Cloud attempt is preserved in telemetry.
- Runtime fallback selects Edge.
- Edge execution succeeds.
- Final completion is true.
- Fallback count is 1.

Observed execution path:

`cloud failure -> edge fallback -> success`

This experiment demonstrates routing resilience and fallback behavior.

It does not claim measured physical distributed-network performance,
because the current runtime deliberately preserves a remote-compatible
execution seam while executing on one machine.

The D metrics layer can consume runtime records using:

- `node`
- `execution_node`
- `deployment_target`

and aggregate:

- Device task count.
- Edge task count.
- Cloud task count.
- Node failure count.
- Node duration.

