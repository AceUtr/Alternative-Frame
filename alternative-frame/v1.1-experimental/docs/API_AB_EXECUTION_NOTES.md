# A/B execution notes

Read these corrections before following the companion Chinese task sheet.

- Use long-horizon mode (长程任务) with contract preview for fixed exportable acceptance contracts. Standard mode writes run_report.json and does not provide the same contract preview or necessarily state.json and controller events.jsonl.
- Preserve and reuse the first contract's exact semantic contents. If contract reuse is unavailable, report the blocker before formal sampling.
- Group A has no plugin message events by design. Missing instrumentation is unknown, not zero. Comparing A's missing plugin-event count against B's deliveries is invalid.
- The message plugin adds dependency summaries while retaining original context; it may increase tokens. This is not the offline unbounded-broadcast baseline.
- Comparable message counts require equivalent instrumentation of actual model input in BOTH groups. Without it, report message count as unavailable and compare outcomes, requests, usage sources and elapsed time. Do not publish message reduction percentages.
- Record actual commit and source hashes per run. Branch names do not freeze source. Local Windows paths in the task sheet identify historical lead-machine artifacts, not teammate-machine paths.
