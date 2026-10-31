# Final Competition Evaluation

Generated: 2026-10-31T02:35:32.588489+00:00

## 1. Single Agent vs Multi Agent

Both deterministic conditions completed all tasks.

- Single Agent completion: 100%
- Multi Agent completion: 100%
- Single Agent mean duration: 0.4027s
- Multi Agent mean duration: 0.3225s
- Multi Agent wall-clock speedup: 1.249x
- Multi Agent mean parallel overlap: 0.0800s

**Supported conclusion:** multi-agent role topology exposes available DAG parallelism and reduces wall-clock duration in the controlled workload.

This experiment does not establish superior LLM reasoning quality.

---

## 2. Recovery OFF vs Recovery ON

### Recovery OFF

- completed: False
- local recovery cycles: 0
- execution trace: `['prepare', 'compute']`

### Recovery ON

- completed: True
- local recovery cycles: 1
- execution trace: `['prepare', 'compute', 'compute', 'verify']`

The successful predecessor is not rerun.

**Supported conclusion:** local DAG recovery repairs the impacted subgraph while preserving unaffected successful work.

---

## 3. Contract OFF vs Contract ON

Both conditions receive the same successful phase report.

### Contract OFF

- phase report: success
- declared complete: True

### Contract ON

- phase report: success
- declared complete: False
- missing criteria: `['final_evidence']`

**Supported conclusion:** global contract validation prevents false completion when required final evidence is missing.

---

## 4. Fixed Cloud vs Dynamic Device/Edge/Cloud Routing

A cloud outage is injected into the same compute workload.

### Fixed Cloud

- completed: False
- final node: cloud
- fallback count: 0
- execution attempts: 1
- cloud attempts: 1
- edge attempts: 0

### Dynamic Routing

- completed: True
- final node: edge
- fallback count: 1
- execution attempts: 2
- cloud attempts: 1
- edge attempts: 1

Execution path:

`cloud failure -> edge fallback -> success`

**Supported conclusion:** under the controlled cloud-outage condition, fixed Cloud placement fails, while the real NodeRouter/RuntimeExecutor path preserves the failed Cloud attempt and successfully falls back to Edge.

This is a deterministic routing resilience experiment, not a claim about physical distributed network performance.

---

## 5. Recorded Real Research Evidence

### Normal

- final goal completed: True
- completed tasks: 8
- cumulative planned tasks: 8
- first-pass successes: 8
- local recovery cycles: 0
- phases: 2

### Local Recovery Sample

- final goal completed: True
- completed tasks: 8
- cumulative planned tasks: 11
- first-pass successes: 7
- local recovery cycles: 1
- phases: 2

Historical recorded runs are genuine project execution evidence, but they are not controlled treatment-vs-control experiments.

Do not describe `8 / 11` as a 72.7% final-goal success rate.

---

# Final Controlled Evidence Matrix

| Experiment | Control | Treatment | Result |
|---|---|---|---|
| Agent topology | Single backend | Multi-agent backends | Same completion, 1.249x wall-clock speedup |
| Local recovery | Recovery OFF | Recovery ON | Failed -> completed |
| Contract validation | Contract OFF | Contract ON | False completion -> missing evidence detected |
| Edge/cloud routing | Fixed Cloud | Dynamic routing | Cloud failure -> Edge fallback success |

---

# Evidence Boundaries

- `deterministic_controlled_run`: mechanism-level controlled evidence.
- `recorded_real_run`: genuine historical execution evidence.
- `live_real_run`: reserved for future API model experiments.

Unknown telemetry must remain unknown.

Do not claim live LLM improvement until live experiments are actually run.

Do not describe this single-machine edge/cloud runtime as measured physical network performance.
