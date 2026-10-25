# Milestone 5: StructuredGoalContractGenerator

Date: 2026-07-21

## Outcome

API long-horizon mode now creates a structured final-goal acceptance contract and requires explicit user confirmation before any Agent or workspace tool executes. Stub long-horizon mode uses the same confirmation gate for its plan-derived contract.

```text
user goal
  -> initial plan hint
  -> StructuredGoalContractGenerator
  -> ContractValidator
  -> user preview / safe JSON edit / confirmation
  -> frozen AcceptanceContract
  -> LongHorizonController execution
  -> StructuredGlobalEvaluator
```

## Contract Content

The generated strict JSON contract contains:

- a concise goal summary;
- atomic required and optional criteria;
- `file_exists`, `command`, `metric`, `semantic`, or `manual` check types;
- relative artifact paths;
- safe verification commands;
- metric names and thresholds;
- constraints faithfully derived from the user goal.

The original goal is supplied by the runtime and cannot be replaced by the model.

## Validation and Safety

`ContractValidator` rejects:

- empty contracts;
- contracts without a required criterion;
- duplicate or malformed criterion IDs;
- unsupported check types;
- non-boolean required flags;
- absolute paths and `..` traversal;
- multiline commands, shell control operators, redirection, and pipelines;
- destructive commands;
- executables outside the verification allowlist;
- malformed metric names and non-numeric thresholds;
- more than 40 criteria.

If the first response is invalid, the exact validation error is returned to the model for one correction attempt. A second invalid response raises `StructuredContractError` before LongHorizonController starts.

## Persistence and UI

The UI presents the goal summary, every required/optional criterion, check type, verification path/command/metric, and constraints. Users may edit the complete JSON, but every edit is revalidated against the original goal and the same path/command safety policy. Cancelling releases the UI and does not start the controller, Agents, or tools.

The confirmed contract is stored in `LongHorizonState.acceptance_contract` and persisted in `state.json`. UI logs show generation attempts, validation failures, waiting/confirmation state, and the final required/total criterion counts.

## Verification

```text
Run `python -B -m pytest -q -p no:cacheprovider` for the current result.
```

Tests cover valid generation, safe UI JSON edits, original-goal immutability, unsafe paths, dangerous commands, non-boolean required flags, duplicate IDs, serialization round trips, and state persistence.

## Current Boundary

- Contract confirmation currently applies to long-horizon mode; standard single-stage multi-Agent mode does not show this dialog.
- The generator uses the current rule-based initial Plan only as a hint; it is not allowed to trust that Plan as complete.
- Semantic criteria still require the later StructuredGlobalEvaluator and run-provenanced evidence.
