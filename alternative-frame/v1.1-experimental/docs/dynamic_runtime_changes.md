# Runtime Requirement Changes

The v1.1 long-horizon controller can accept a new, additive acceptance condition while a task is running. It consumes the request after the current phase finishes, reevaluates that phase under the updated contract, and asks the planner for another phase when the new condition is not yet met.

## Use From The UI

1. Select `长程任务` and start the task as usual.
2. When the controller is ready, select `追加运行中要求`.
3. Enter one required condition. Choose `semantic` for a model-reviewed condition or `file_exists` and a workspace-relative path for a required output.
4. Submit once. The button stays unavailable until the controller accepts or rejects the request. The collaboration log records the contract revision and the request file path.

Requests only add requirements. Existing conditions cannot be removed or weakened. File paths must be relative to the run workspace and cannot escape it. A completed run rejects late requests. Requests are scoped to one run ID and contract revision; stale revisions are rejected.

The visible state and audit trail are under `runs/long_horizon/<run-id>/`: `state.json`, `events.jsonl`, `runtime_changes/pending/`, `runtime_changes/accepted/`, `runtime_changes/rejected/`, and immutable contract snapshots under `runtime_changes/contracts/`.

## Evaluation Behavior

The deterministic Stub evaluator does not claim semantic completion. A semantic condition remains deferred and the run stays incomplete. A `file_exists` condition also needs an artifact record from this run; an unrelated file already present in the workspace does not satisfy it. With API mode, the structured evaluator applies the hard evidence checks first and may use the configured model for semantic review.

The controller evaluates outside the inbox lock. Before persisting a phase result or marking the run completed, it locks the inbox and checks for requests that arrived during evaluation. If the contract changed, it reevaluates against the new contract. This keeps the phase record, final evaluation, contract revision, and completion status aligned.

## Evidence Boundary

`core.long_horizon.runtime_change_acceptance` runs a deterministic controlled scenario with a separate local injector process. It exercises the same request submission API, inbox, contract update, evaluator, planner, and persisted phase state used by the UI. The run produces a summary and SHA-256 manifest. This demonstrates local external-process change handling; it is not a live-API quality result or a second-device network test.

The separate Edge/Cloud fault-recovery demo covers injected worker failure and failover. It must pass the strict cross-host verifier with logs from a genuinely different machine before it can be described as dual-device evidence.
