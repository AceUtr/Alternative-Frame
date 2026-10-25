# Milestone 9: Intra-phase DAG recovery and evidence visualization

## Three-level recovery

The runtime now uses three bounded recovery levels:

1. Task retry: the same Agent receives acceptance failures and retries the task.
2. Intra-phase DAG recovery: successful independent nodes are frozen; failed nodes and all downstream blocked nodes form a minimal recovery subgraph.
3. Cross-phase replanning: the GlobalEvaluator opens a new phase only when local recovery cannot satisfy the final contract.

`FailureImpactAnalyzer` derives failed, blocked, impacted, and frozen node sets from the original phase plan and report. `RecoverySubgraphGenerator` preserves dependencies inside the impacted set and removes dependencies already satisfied by frozen nodes. Each recovery task receives `local_recovery_feedback` containing the prior status, failures, summary, frozen predecessors, recovery cycle, and any conservative role replacement.

`LocalDAGRecoveryController` executes a bounded number of recovery cycles. Re-executed nodes count against the long-horizon task budget. Its merged report contains successful frozen results plus the newest results for impacted nodes, so the GlobalEvaluator evaluates one coherent phase result. Local recovery events are persisted to `events.jsonl`, while each `PhaseRecord` stores the recovery cycle count and actual number of task executions.

## UI visualization

The collaboration panel now has three views:

- Task table: role, dependencies, status, and attempts.
- DAG: dependency arrows and stable task nodes with live status colors.
- Acceptance evidence: every deterministic contract criterion with passed, failed, or deferred status and its concrete evidence or rejection reason.

When local recovery starts, affected nodes are marked as recovering. The recovery subgraph replaces the graph view for the active cycle, while logs record frozen nodes, impacted nodes, recovered nodes, and remaining failures. Hard-gate evaluation automatically opens the evidence view.

## Safety properties

- Successful independent nodes are not re-executed.
- A recovery subgraph cannot escape the original task set.
- Recovery execution is bounded by local cycles and the global task budget.
- A role is changed only for a small set of compatible failure/task shapes and only when the replacement role is registered.
- Local success does not bypass contract evaluation; the merged report still passes through the GlobalEvaluator.
