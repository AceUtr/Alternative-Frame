# Milestone 8: Contract-native DAG and resilient replanning

Date: 2026-07-23

## Contract-native initial planning

Long-horizon execution no longer runs the domain template as its initial DAG. The template may be supplied only as a contract-generation hint. After user confirmation, `StructuredInitialDAGGenerator` creates a new DAG directly from the frozen acceptance contract.

The plan is rejected before execution unless:

- every required criterion has exactly one task owner;
- every required file has exactly one creator;
- the criterion owner and file creator are the same task;
- every output path appears in the confirmed contract;
- dependencies are acyclic;
- roles and tools stay within the permission map;
- commands and paths pass the existing safety validators.

If the model returns an empty, malformed, unrelated, or unsafe plan twice, `RuleBasedContractPlanner` groups criteria into implementation, tests, documents, experiments, exact command verification, and semantic review. It never falls back to the former authentication-specific software template.

## Resilient replanning

`StructuredReplanner` now catches transport and parsing failures inside its bounded attempt loop and emits retry/backoff events. `ResilientReplanner` uses `DeterministicRecoveryPlanner` when the model remains unavailable. The deterministic planner creates the smallest DAG that owns only the criteria reported missing by `StructuredGlobalEvaluator`.

If both primary and fallback recovery are unavailable, `LongHorizonController` persists a `replan_pending` event and returns a paused, resumable state rather than losing the run as a terminal failure.

## UI controls

API mode exposes:

- `API Timeout` (10-600 seconds, default 120);
- `Replan Attempts` (1-5, default 2).

The log distinguishes structured initial planning, validation correction, rule fallback, Replanner backoff, deterministic recovery, and resumable replan-pending state.

## Recovery of the observed run

Run `91e078831d87` can be selected from **运行历史** after restarting the UI. Since phase 1 and its evidence are persisted, resume starts from recovery planning and does not regenerate or rerun the old authentication-template phase.
