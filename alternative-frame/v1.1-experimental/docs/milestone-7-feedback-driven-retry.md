# Milestone 7: Feedback-driven task retry

Date: 2026-07-23

## Outcome

Task retries are no longer identical blind reruns. Every tool-calling Agent receives a complete task contract containing exact expected outputs, allowed tools, structured acceptance checks, and completion rules. When task-level acceptance fails, the Orchestrator classifies the failure and injects structured correction feedback into the next attempt.

```text
Agent attempt
  -> task acceptance and run-provenance check
  -> failure classification
  -> structured RetryFeedback
  -> corrected Agent attempt
  -> acceptance
```

## Retry feedback

Feedback records the next attempt number, failure category, exact failures, previous summary, successful artifacts retained from earlier attempts, and concrete correction directives. Missing artifacts instruct the Agent to write exact relative paths; missing command evidence instructs it to run the exact contract command and repair failures until exit code zero.

Successful artifacts and tool evidence accumulate across attempts within the same task. Previous failure messages do not contaminate a later successful result.

## Evidence requirements

A file check now requires both filesystem existence and evidence that the current task run wrote the artifact. Stale files do not pass. Windows and POSIX separators are normalized, and directory outputs such as `tests/` are proven by a run-provenanced child artifact.

## Safety and budgets

Retries remain bounded by `SubTask.max_retries`. Permission, authentication, role, and tool-capability errors stop immediately. Repeated identical tool calls and maximum tool-step failures are escalated to phase replanning instead of repeating the same expensive loop.

The UI logs each attempt and the failure that scheduled a corrective retry.
