# Unified Evaluation Report

Generated: 2026-08-14T05:29:23.065964+00:00

## Evidence classes

This report deliberately separates three evidence classes.

1. `deterministic_controlled_run`
   - controlled mechanism-level ablation;
   - identical inputs and deterministic failures;
   - no LLM API required.

2. `recorded_real_run`
   - previously recorded real research-demo executions;
   - reflects genuine project execution history;
   - not a controlled randomized comparison.

3. `live_real_run`
   - reserved for future live model experiments after an API model is configured;
   - no live-model claims are made in this report yet.

## 1. Controlled local-recovery ablation

The same three-node DAG is executed in both conditions:

`prepare -> compute -> verify`

The first execution of `compute` fails deterministically.

| Mode | Final result | Local recovery | Execution trace |
|---|---|---:|---|
| recovery_off | FAIL | 0 | `['prepare', 'compute']` |
| recovery_on | PASS | 1 | `['prepare', 'compute', 'compute', 'verify']` |

### Finding

Recovery disabled leaves the workflow failed after the injected computation failure.

Recovery enabled performs one local recovery cycle and completes the workflow.

The successful `prepare` predecessor is not rerun. Only the impacted `compute` node and blocked downstream `verify` node are executed during recovery.

Therefore this experiment demonstrates both **recoverability** and **recovery locality**.

## 2. Controlled contract-validation ablation

Both modes receive the same green phase report.

`calculator.py` exists with artifact provenance and the exact required test command has successful exit-code-0 evidence.

`FINAL_EVIDENCE.md` is deliberately omitted.

| Mode | Phase report | Completion decision | Missing criteria |
|---|---|---|---|
| contract_off | success | True | [] |
| contract_on | success | False | ['final_evidence'] |

### Finding

Without global contract validation, a successful phase report is declared complete.

With contract validation enabled, the same execution is correctly rejected because `final_evidence` is missing.

This demonstrates that contract validation prevents **false completion** rather than merely checking whether individual agents returned `success`.

## 3. Recorded real research runs

| Run | Final goal | Completed | Cumulative planned | First-pass | Local recovery | Phases |
|---|---|---:|---:|---:|---:|---:|
| research_normal | True | 8 | 8 | 8 | 0 | 2 |
| research_local_recovery | True | 8 | 11 | 7 | 1 | 2 |

### Finding

Both historical research runs eventually completed the final goal.

The local-recovery run contains one real local-recovery event and accumulated additional planned work.

`8 / 11` must **not** be described as a 72.7% final-goal success rate. The denominator includes recovery-introduced work, while the final goal itself completed.

## 4. Current evidence summary

| Claim | Evidence |
|---|---|
| Local recovery can repair an injected DAG failure | deterministic controlled ablation |
| Local recovery avoids rerunning a successful unaffected predecessor | deterministic execution trace |
| Contract validation can prevent false completion | deterministic controlled ablation |
| Local recovery has occurred in a real research run | recorded real run |
| Multi-phase contract completion has occurred in real research runs | recorded real run |
| Live LLM recovery improves completion rate | **not yet established** |
| Single-agent vs multi-agent advantage | **not yet established** |
| Dynamic device/edge/cloud advantage | **not yet established** |

## 5. Measurement caveats

- Missing token usage is `unknown`, not zero.
- Missing model cost is `unknown`, not zero.
- Historical research samples do not contain reliable device/edge/cloud placement evidence.
- Recorded historical runs are observational evidence, not controlled treatment-vs-control experiments.
- Deterministic experiments isolate mechanism behavior but should not be presented as live LLM performance measurements.
- Live model ablations will be added once model API access is available.

## Source benchmark files

- Recorded research: `benchmarks\results\summary\research_recorded-20260814T045729288642Z.json`
- Recovery ablation: `benchmarks\results\summary\deterministic_recovery-20260814T052059930828Z.json`
- Contract ablation: `benchmarks\results\summary\deterministic_contract-20260814T052657961412Z.json`
