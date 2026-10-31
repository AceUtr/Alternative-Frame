# Evaluation Methodology

## 1. Purpose
The evaluation layer measures execution reliability, recovery behavior, contract correctness, orchestration efficiency, and routing resilience.

Evidence classes are kept separate and must not be silently mixed.

## 2. Evidence Classes

### deterministic_controlled_run
Used for:
- Single Agent vs Multi Agent
- Recovery OFF vs ON
- Contract validation OFF vs ON
- Fixed Cloud vs Dynamic Routing

Suitable for mechanism-level claims, not superior LLM reasoning quality or physical network-performance claims.

### recorded_real_run
Historical real project runs. They show that mechanisms such as local recovery and multi-phase completion occurred in genuine executions, but are not controlled treatment-vs-control experiments.

### live_real_run
Reserved for future API model experiments. No live-model claim is made before running them.

## 3. Core Metrics
Final completion, task counts, first-pass success, retries, local recovery, phases, wall-clock duration, model calls, tokens, estimated cost, tool success, human interventions, device/edge/cloud/unknown counts, per-node failures, and per-node duration.

## 4. Unknown Values
Missing observations remain unknown, never coerced to zero.

## 5. Controlled Experiments

### 5.1 Single Agent vs Multi Agent
- completion: 100% / 100%
- mean duration: 0.4041 s / 0.3247 s
- wall-clock speedup: 1.245x
- multi-agent mean parallel overlap: 0.0802 s

Conclusion: orchestration parallelism benefit under controlled deterministic task logic.

### 5.2 Recovery OFF vs Recovery ON
DAG: `prepare -> compute -> verify`

- OFF: failed; trace `prepare, compute`
- ON: completed; one local recovery; trace `prepare, compute, compute, verify`

The successful predecessor is frozen and not rerun.

### 5.3 Contract Validation OFF vs ON
Same successful phase report; `FINAL_EVIDENCE.md` deliberately missing.

- OFF: completed = true
- ON: completed = false; missing `final_evidence`

Conclusion: global contract validation prevents false completion.

### 5.4 Fixed Cloud vs Dynamic Device/Edge/Cloud Routing
Status: PASS — deterministic controlled evidence.

Integrated runtime: `NodeRouter`, `TaskRequirements`, `RuntimeExecutor`, `DeviceNode`, `EdgeNode`, `CloudNode`.

- Fixed Cloud: failed, no fallback.
- Dynamic Routing: Cloud selected first, failed attempt preserved, Edge fallback succeeds, fallback count = 1.

Observed path: `cloud failure -> edge fallback -> success`

This demonstrates routing resilience, not measured physical distributed-network performance.

## 6. Recorded Research Evidence
Two recorded real research runs show final-goal completion, multi-phase execution, contract completion, and one real local-recovery event.

Do not interpret `8 / 11` as a 72.7% final-goal completion rate; the denominator includes recovery-added planning work.

## 7. Reproducibility
Use unique run IDs, isolated workspaces, append-only raw outputs, separate summaries, and tests that do not depend on ignored artifacts from previous local runs.

## 8. Current Validation Status
- D focused suite: 49 passed
- Full C+D repository: 163 passed, 0 failed
- C routing/runtime focused suite: 34 passed
- Deterministic routing ablation: 4 passed

Device/edge/cloud routing evaluation is complete. Live LLM experiments remain optional and deferred.

## 9. Routing Telemetry Integration
The metrics layer consumes `node`, `execution_node`, and `deployment_target`, aggregating device/edge/cloud/unknown task counts, node failures, and node duration.

## 10. Evidence Boundaries
Do not:
- present deterministic timing as proof of superior LLM intelligence;
- present historical runs as controlled experiments;
- convert unknown telemetry to zero;
- describe single-machine routing as measured physical network performance;
- present smoke/stub values as competition performance.
