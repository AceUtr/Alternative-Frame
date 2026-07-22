# Milestone 6: Contract-driven planning and resumable UI

Date: 2026-07-22

## Contract-driven initial DAG

After the user confirms the acceptance contract, `ContractAwarePlanner` rebuilds the initial DAG from the domain baseline and the frozen contract. Every required criterion is assigned to one or more tasks through `metadata.contract_criteria`, and its executable check is copied into the owning task. `ContractCoverageValidator` rejects a DAG when any required criterion has no owner.

The runtime order is now:

```text
goal -> baseline hint -> contract generation -> user confirmation
     -> ContractAwarePlanner -> coverage and permission validation
     -> LongHorizonController
```

## Safe pause and resume

The UI pause button requests a phase-boundary pause. Running Agent work is allowed to finish, then state and evidence are atomically persisted with a `run_paused` event. This avoids corrupting task evidence or leaving a half-written phase record.

The run-history window lists persisted runs newest first. A paused, interrupted, failed, or budget-limited run can be selected for resume. The frozen goal and acceptance contract are loaded from `state.json`; completed phases are not rerun. API keys remain UI/process-memory only and are never persisted.

## Real two-phase evidence run

`run_real_two_phase_demo.py` provides a controlled real-model scenario. Phase one implements and tests a calculator but the independent audit deliberately reports the missing `FINAL_EVIDENCE.md` without repairing it. The hard evidence gate must report `final_evidence` missing, `StructuredReplanner` must create a recovery DAG, and a later phase must complete the contract.

```powershell
$env:MODEL_BASE_URL = "your CCswitch OpenAI-compatible base URL"
$env:MODEL_API_KEY = "your temporary key"
$env:MODEL_NAME = "your model name"
python run_real_two_phase_demo.py
```

The script exits unsuccessfully unless all of these are true:

- phase one records `final_evidence` as missing;
- replanning produces at least one later phase;
- the final state is `completed`;
- the persisted state contains at least two phase records.

## Current pause boundary

Pause is cooperative at phase boundaries. It does not forcibly terminate an Agent or tool call already in progress. A process crash during a phase retains the pending plan, so resuming may rerun that incomplete phase; individual tools and Demo tasks should therefore remain idempotent.
