# Milestone 3: LongHorizonController MVP

Date: 2026-07-21

## Outcome

Alternative Frame now has a bounded long-horizon control layer above the existing Orchestrator. The controller can execute a phase, evaluate progress against the global goal, request a revised phase plan, persist state, and continue until completion or budget exhaustion.

## Execution Model

```text
goal
  -> initial phase plan
  -> persist pending plan
  -> Orchestrator executes phase DAG
  -> global evaluator
     -> completed: persist final state
     -> incomplete: replanner creates next phase
  -> repeat within phase/task budgets
```

## Implemented Capabilities

- Bounded phase loop with `max_phases`.
- Aggregate task budget with `max_total_tasks`.
- Global evaluation contract returning reason, failures, evidence, and next focus.
- Injectable initial planner, evaluator, and replanner.
- Atomic `state.json` replacement.
- Append-only `events.jsonl` execution trail.
- Serializable Plan snapshots for pending phases.
- Resume of a persisted pending phase.
- Aggregated completed tasks, failed tasks, artifacts, decisions, and phase records.
- Explicit `completed`, `failed`, and `budget_exhausted` terminal outcomes.

## Verification

Framework regression suite:

```text
12 passed in 0.17s
```

Offline long-horizon demonstration:

```text
phase 1: implementation -> incomplete (independent verification missing)
phase 2: test + review -> completed
status=completed phases=2 tasks=3
```

## Run

```powershell
cd "E:\Users\wang\Documents\plan a project\alternative-frame\v0.1"
python run_long_horizon_demo.py
```

To select another persistence root:

```powershell
$env:LONG_HORIZON_RUNS_DIR = "$env:TEMP\alternative-frame-long-horizon"
python run_long_horizon_demo.py
```

## Current Boundary

- Resume is currently phase-level: a pending phase is rerun after interruption.
- Mid-task checkpointing and exactly-once tool execution are not yet implemented.
- The default evaluator treats a successful phase as global completion; real domains must inject stronger global acceptance logic.
- The current demo uses deterministic Agents to validate the controller independently of API reliability.
- UI integration and real-model replanning are the next steps.

## UI Integration

The task mode selector now exposes two normal user workflows:

- `标准多 Agent`: execute one planned DAG with the existing Orchestrator.
- `长程任务`: execute through LongHorizonController with up to three phases and 50 aggregate tasks.

Long-horizon UI events show phase planning, the current phase DAG, global evaluation decisions, budget exhaustion, final status, and the persisted state path.

The tool creation and failure-repair self-tests remain available behind the `开发者模式` checkbox. They are diagnostics for model/tool connectivity and are intentionally hidden from the default competition workflow.

In API mode, recovery now uses `StructuredReplanner`. It sends the global goal, prior failures, artifacts, decisions, evaluation, and remaining budgets to the configured model. The model must return a strict JSON DAG. `PlanValidator` rejects unknown roles, tool escalation, unsafe output paths, invalid checks, missing dependencies, cycles, and task-budget overflow before the plan reaches Orchestrator.

If the first model response is invalid, the validation error is returned to the model for one correction attempt. A second invalid response terminates replanning explicitly. UI logs show replanning attempts, validation failures, and the accepted recovery plan size.

Local Stub mode retains the deterministic recovery planner so the controller can be demonstrated without an API.
