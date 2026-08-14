# Competition Demo Script

Target duration: 8–12 minutes.

## 0:00–0:45 — Problem

Explain the core problem:

Long-running agent workflows can fail because one task fails,
because a final requirement is silently omitted, or because the
system incorrectly declares success based only on individual
agent outputs.

Alternative-Frame addresses this with:

- role-based multi-agent DAG execution;
- local DAG recovery;
- multi-phase recovery;
- explicit acceptance contracts;
- evidence-based evaluation.

## 0:45–2:00 — Architecture

Show the main execution flow:

Goal
-> Acceptance Contract
-> DAG Plan
-> Role-based Agents
-> Real Tools
-> Evidence
-> Global Evaluation
-> Recovery when required
-> Final acceptance

Point out that evaluation is not based only on agent-generated
text.

## 2:00–3:15 — Multi-Agent DAG

Show a DAG with independent branches.

Explain that the Orchestrator schedules ready nodes while
respecting dependencies.

Show the controlled result:

- Single Agent completion: 100%.
- Multi Agent completion: 100%.
- Single Agent mean wall-clock: use generated report value.
- Multi Agent mean wall-clock: use generated report value.
- Controlled speedup: use generated report value.

Important wording:

This experiment demonstrates orchestration parallelism under
identical deterministic task logic. It does not claim that a
deterministic multi-agent system is smarter.

## 3:15–4:45 — Local Recovery

Show:

prepare -> compute -> verify

Inject the deterministic first failure in `compute`.

Recovery OFF:

- compute fails;
- verify is blocked;
- workflow fails.

Recovery ON:

- failure-impact analysis identifies compute and verify;
- prepare is frozen;
- recovery subgraph contains only compute and verify;
- compute succeeds on recovery;
- verify succeeds;
- workflow completes.

Show execution trace:

Recovery OFF:
`prepare, compute`

Recovery ON:
`prepare, compute, compute, verify`

Emphasize that `prepare` is not rerun.

## 4:45–6:15 — Contract Validation

Show a green phase report with:

- calculator source present;
- test evidence present;
- FINAL_EVIDENCE.md missing.

Contract OFF:

phase_status = success
completion = true

Contract ON:

phase_status = success
completion = false
missing = final_evidence

Explain:

Without global contract validation, the system produces a false
completion.

With the contract enabled, it correctly refuses to declare the
goal complete.

## 6:15–7:30 — Real Recorded Research Run

Switch from deterministic evidence to recorded real evidence.

Explicitly say:

The following evidence comes from previously recorded real
research-demo runs, not from the deterministic fixtures.

Show:

research_normal:
- final goal completed;
- 8 completed tasks;
- no local recovery.

research_local_recovery:
- final goal completed;
- one real local-recovery event;
- additional recovery planning work;
- multi-phase completion.

Do not present `8/11` as a final-goal success percentage.

## 7:30–8:30 — Evaluation Dashboard

Show:

- unified comparison CSV;
- agent wall-clock figure;
- recovery completion figure;
- contract decision figure;
- recorded research figure.

Explain the evidence classes:

- deterministic controlled;
- recorded real;
- live real.

This separation prevents benchmark claims from becoming stronger
than the underlying evidence.

## 8:30–9:15 — Token and Cost Accounting

Explain that the schema supports:

- prompt tokens;
- completion tokens;
- total tokens;
- estimated cost.

If telemetry is absent, display `unknown`, never fake `0`.

If live API experiments have not been run, say so explicitly.

## 9:15–10:00 — Device / Edge / Cloud

If the routing module is ready:

show fixed placement vs dynamic routing.

Show:

- per-node task counts;
- per-node failures;
- per-node duration;
- cost / latency comparison if available.

If the routing module is not ready:

state that routing evaluation is reserved in the schema but no
routing-performance claim is currently made.

## 10:00–10:45 — Final Summary

Summarize only evidence-backed conclusions:

1. Multi-agent topology exposes real DAG parallelism.
2. Local recovery can repair an impacted subgraph without
   rerunning a successful unaffected predecessor.
3. Contract validation prevents false completion.
4. Recovery and multi-phase completion have occurred in real
   recorded research runs.
5. Live LLM and routing conclusions are reported only after the
   corresponding evidence exists.

## Failure Fallback

If a live demo fails:

1. Do not restart repeatedly on stage.
2. Show the latest persisted state and events.
3. Open the recorded benchmark output.
4. Show the deterministic controlled experiment.
5. Explain the failure using actual evidence.
6. Never replace a failed live result with an unlabelled
   historical result.

The fallback itself demonstrates the project's persistence,
auditability, and evaluation discipline.
