# Milestone 4: Reliable Final-Goal Completion

Date: 2026-07-21

## Outcome

Alternative Frame no longer equates a green phase or an Agent success message with final-goal completion. API long-horizon mode now uses a frozen acceptance contract, deterministic evidence gates, and conservative structured semantic evaluation.

Final completion requires:

```text
phase execution success
AND required hard evidence gates pass
AND structured semantic goal coverage returns completed=true
```

## Evidence Chain

- `FileEditor.write` records the relative artifact path and write provenance.
- `TestRunner` records its exact command, success, exit code, and test counts.
- `ExperimentRunner` records its exact command and parsed metrics.
- `ToolCallingAgent` stores structured tool records on `AgentResult`.
- `LongHorizonState` persists tool evidence across phases.
- The global evaluator can reuse prior test evidence after a later documentation or review phase.

## Hard Evidence Gates

Hard gates cannot be overridden by the semantic model.

- A required file must exist inside the workspace.
- A pre-existing file is insufficient unless the current long-horizon run has artifact provenance for it.
- A required command must match the declared command after whitespace normalization.
- The matching command must have `success=true` and `exit_code=0`.
- A metric with a declared name and threshold must be present in structured experiment evidence.
- Any failed phase report blocks completion.

Manual and semantic criteria are deferred to structured semantic review after all hard gates pass.

## Semantic Evaluation

`StructuredGlobalEvaluator` receives the final user goal, acceptance contract, hard-gate report, task results, run-provenanced artifacts, structured tool evidence, and prior decisions. It must return one strict JSON object containing:

- `completed`
- `reason`
- `satisfied_criteria`
- `missing_criteria`
- `failures`
- `next_focus`
- `evidence`

Malformed or unavailable model evaluation fails closed: it can never mark the final goal complete.

## Verified False-Completion Scenario

The end-to-end regression scenario deliberately makes every phase-1 Agent return `success` while omitting `README.md`.

```text
phase 1 report = success
hard gate = failed (README missing and no provenance)
completed = false
phase 2 = create README
hard gate = passed using prior test evidence + current README artifact
semantic evaluation = completed
```

## Verification

```text
26 passed in 0.25s
```

The suite covers stale-file rejection, exact-command matching, non-zero exits, cross-phase evidence persistence, malformed semantic responses, and the green-tasks-but-incomplete-goal scenario.

## Current Boundary

- The acceptance contract is currently derived from the initial Plan. A future model-driven intent contract generator should extract richer user-specific criteria before execution.
- File provenance is recorded for FileEditor writes; files created indirectly by shell commands are not automatically attributed.
- Metric direction currently assumes higher-is-better when a numeric threshold is supplied.
- Semantic evaluation remains dependent on the configured API, but API failure is conservative and cannot produce a false success.
