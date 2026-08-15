# Competition Demo Script

Target duration: 8–12 minutes.

## 0:00–0:45 — Problem
Long-running agent workflows can fail because one task fails, a final requirement is omitted, or the system declares success too early.

Alternative-Frame addresses this with multi-agent DAG execution, local recovery, multi-phase recovery, acceptance contracts, dynamic routing, and evidence-based evaluation.

## 0:45–2:00 — Architecture
Goal -> Acceptance Contract -> DAG Plan -> Role-based Agents -> Real Tools -> Evidence -> Global Evaluation -> Recovery / Runtime Routing -> Final acceptance

## 2:00–3:15 — Multi-Agent DAG
- Single Agent completion: 100%
- Multi Agent completion: 100%
- Single mean wall-clock: 0.4041 s
- Multi mean wall-clock: 0.3247 s
- Speedup: 1.245x
- Multi mean parallel overlap: 0.0802 s

Say explicitly: this demonstrates orchestration parallelism, not superior LLM reasoning quality.

## 3:15–4:45 — Local Recovery
DAG: `prepare -> compute -> verify`

OFF: `prepare, compute` -> failed

ON: `prepare, compute, compute, verify` -> completed

Emphasize that `prepare` is not rerun.

## 4:45–6:15 — Contract Validation
Same green phase report; `FINAL_EVIDENCE.md` missing.

- Contract OFF: completed = true
- Contract ON: completed = false; missing = `final_evidence`

Explain that the contract prevents false completion.

## 6:15–7:15 — Recorded Real Research
State clearly that these are recorded real runs, not deterministic fixtures.

`research_normal`: final goal completed, 8 completed tasks, no local recovery.

`research_local_recovery`: final goal completed, one real recovery event, extra recovery planning work, multi-phase completion.

Do not present `8/11` as final-goal success percentage.

## 7:15–8:00 — Evaluation Dashboard
Show final comparison CSV and figures for agent speed, recovery, contract, routing, and recorded research.

Explain evidence classes: deterministic controlled, recorded real, live real.

## 8:00–8:40 — Token and Cost Accounting
Missing telemetry stays `unknown`, not `0`.

Live API experiments are optional/deferred; no live-model improvement claim is made.

## 8:40–9:40 — Device / Edge / Cloud Routing
Fixed Cloud:
- completed = false
- final node = cloud
- fallback = 0
- attempts = 1

Dynamic Routing:
- completed = true
- final node = edge
- fallback = 1
- attempts = 2

Trace: `Cloud attempt -> injected failure -> Edge fallback -> success`

Mention sensitive-data-on-device, low-latency edge selection, and hard filters for capability, cost, latency, network, and privacy.

Say explicitly: this is routing-resilience evidence using the real runtime, not physical distributed-network latency measurement.

## 9:40–10:30 — Final Summary
1. Multi-agent topology preserved 100% completion and produced 1.245x wall-clock speedup in the controlled workload.
2. Local recovery repaired only the impacted subgraph.
3. Contract validation prevented false completion.
4. Dynamic routing recovered from Cloud failure by falling back to Edge.
5. Recorded real runs show recovery and multi-phase completion occurred in genuine project execution.
6. Live LLM claims remain deferred.

## Failure Fallback
If a stage demo fails, show persisted state/events, recorded benchmark output, and deterministic controlled evidence. Never relabel historical results as live results.
