# Milestone 2: Real Model Tool-Calling Repair Loop

Date: 2026-07-21

## Outcome

Alternative Frame v0.1 completed an end-to-end real-model software repair loop through an OpenAI-compatible API:

1. The model received an isolated software task.
2. The Agent called workspace-scoped file tools.
3. The Agent executed a real unittest command.
4. The initial test failed with `AssertionError: -1 != 5`.
5. The failure output was returned to the model.
6. The model corrected `hello.py` from subtraction to addition.
7. The Agent executed the same test again and obtained exit code 0.
8. The acceptance layer and Main Agent reported success.

## Implemented Capabilities

- OpenAI-compatible model configuration in the UI.
- Standard `tool_calls` execution through `ToolCallingAgent`.
- Per-tool start/finish events with arguments, result summaries, and duration.
- Isolated `tool_test_workspace` for tool-call verification.
- Dedicated creation and failure-repair self-test modes.
- File creation, shell execution, test execution, feedback, repair, and re-test loop.
- Machine-verifiable acceptance instead of trusting model prose.
- Bounded repeated-call detection and maximum tool steps.
- Bounded retry for TLS/network failures, HTTP 429, and HTTP 5xx responses.

## Verification

Framework regression suite:

```text
9 passed in 0.10s
```

Independent repaired artifact verification:

```text
test_add_two_integers ... ok
Ran 1 test in 0.000s
OK
```

## Current Boundary

This milestone proves a single sub-Agent can complete an observe-act-test-repair loop. It does not yet prove long-horizon execution across multiple phases, persistent recovery after process interruption, dynamic replanning, memory, dynamic topology, or edge-cloud-device scheduling.

The next milestone is a minimal `LongHorizonController` with phased execution, global evaluation, replanning, persisted state, bounded budgets, and resume support.
