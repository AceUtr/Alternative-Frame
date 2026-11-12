# Dynamic Fault and Requirement-Change Acceptance

This acceptance adds two independently injected runtime scenarios to the main `AgentRegistry` → `Orchestrator` → `LongHorizonController` path:

1. A separate process waits until the Cloud worker has started a specific task, then terminates that worker. The controller must detect the transport failure, retry the same task on Edge, preserve and verify the intermediate result, recognize that final packaging is still missing, replan phase 2, and finish the final deliverable without a human pause or resume.
2. A separate process waits until the baseline artifact is complete, then writes a new acceptance criterion into the run-scoped inbox. The controller detects the change, produces a second-phase plan, preserves the baseline artifact, and satisfies the added criterion.

Neither worker has an internal fault-mode flag. The injected event is not passed into the controller. The fault demo exercises deterministic digest and report agents; it proves the main controller's two-phase recovery and delivery path, but not model-generated task planning, provider resilience, or production availability. The saved final report includes the injector, routing, phase-review, and task-completion events so the intermediate decisions can be reviewed.

The organizer's competition PDF was located in the supplied chat-file archive. Clause 5/e, printed page 5, says the deployable system must accept dynamically injected exceptions, requirement changes, or node failures, autonomously complete the full chain from high-level intent to final deliverable without human intervention, and show intermediate decisions and reasoning traces. This acceptance covers external process failure and requirement-change controls; both demos remain deterministic and do not claim arbitrary LLM interpretation.

## Local Process-Fault Control

From `alternative-frame/v1.1-experimental`, run:

```powershell
python -m core.edge_cloud.demo --evidence-dir runs/dynamic_fault_injection --inject-delay-seconds 0.8 --cloud-delay-seconds 5 --cloud-timeout-seconds 2.5
```

The independent injector waits for `worker_task_started` for `remote_digest`, waits the configured interval, then terminates the Cloud PID recorded by the worker. Phase 1 recovers the remote computation and writes `recovered_result.json`; the goal evaluator records that `final_report.json` is still missing and triggers phase 2, which assembles the final deliverable from the retained result and runtime decision trace. This is a same-computer loopback control, not a multi-device result.

The runner exits nonzero unless its execution checks pass. Verify the saved raw evidence separately:

```powershell
python -m core.edge_cloud.evidence runs/dynamic_fault_injection/<run-id> --output runs/dynamic_fault_injection/<run-id>/acceptance_verification.json
```

The verifier reconstructs run/task identity and event ordering, checks that Cloud started but did not finish the task, checks the same task failed over and completed on Edge, confirms both workers ran the same source commit and working-tree fingerprint, verifies the incomplete phase-1 review and accepted phase-2 delivery, binds the final report to the intermediate artifact hash and runtime decision trace, and verifies manifest size/hash records. The output warns when both nodes have the same host identity.

## Dynamic Requirement-Change Control

The regular long-horizon UI now accepts a run-scoped additive condition using `追加运行中要求`. It updates the persisted acceptance contract and is consumed after the current phase finishes. When the new condition is unmet, the controller records the phase as incomplete and invokes the normal replanner. It never removes existing criteria.

Run the controlled acceptance, which uses a separate process to submit a request through the same inbox API as the UI:

```powershell
python -m core.long_horizon.runtime_change_acceptance --evidence-dir runs/runtime_change_acceptance
```

The output includes `summary.json`, `manifest.json`, controller state/events, accepted contract snapshots, injector events, and the baseline/final artifacts. Verify it separately:

```powershell
python -m core.long_horizon.runtime_change_acceptance --verify runs/runtime_change_acceptance/<run-id>
```

This run tests additive contract revision, stale-completion rejection, replanning, and baseline retention in the main controller. It uses deterministic agents on one host and does not make a live-API or second-device claim.

The older dedicated demo remains available for its historical acceptance format:

```powershell
python -m core.long_horizon.dynamic_change_demo --evidence-dir runs/dynamic_requirement_change
```

The older demo is not a substitute for the main-controller runtime-change verifier above. Neither control claims that an LLM understands arbitrary natural-language changes.

## Two-Computer Fault Run

Use the exact same source revision on computers A and B. Use a temporary test token only; never reuse an API key. Keep the Edge log on B until the final copy has been checked. Restrict port 8010 to the private test network and do not expose this demo worker to the public Internet.

On computer B, set the same `AF_EDGE_CLOUD_TOKEN` that will be used on A, then start the Edge worker with a fresh event log:

```powershell
$env:AF_EDGE_CLOUD_TOKEN = Read-Host 'Temporary test token'
python -m core.edge_cloud.worker --host 0.0.0.0 --port 8010 --node-id edge-01 --role edge --event-log runs/edge-worker-events-<run-id>.jsonl
```

On computer A, set that same temporary token and run the main framework against B's private LAN address:

```powershell
$env:AF_EDGE_CLOUD_TOKEN = Read-Host 'Temporary test token'
python -m core.edge_cloud.demo --edge-url http://<computer-B-address>:8010 --evidence-dir runs/dynamic_fault_injection --run-id <run-id> --inject-delay-seconds 0.8 --cloud-delay-seconds 5 --cloud-timeout-seconds 2.5
```

The Cloud worker and independent injector run on A. The injector waits for the Cloud task-start record before killing that process. The framework must route the same task to B's Edge worker. After the run, copy B's exact run-specific event log to:

```text
runs/dynamic_fault_injection/<run-id>/edge_worker_events.jsonl
```

Then run final bundle verification on A:

```powershell
python -m core.edge_cloud.evidence runs/dynamic_fault_injection/<run-id> --register-edge-log --require-edge-log --require-cross-host --output runs/dynamic_fault_injection/<run-id>/acceptance_verification.json
```

The final check first registers the copied Edge log in `manifest.json`, then requires matching run/task IDs, Cloud and Edge event records, the same source commit and working-tree fingerprint, different hostnames and hashed host fingerprints, and intact evidence hashes. A successful HTTP request to a LAN address alone is not a two-computer acceptance. The verifier's result plus the copied Edge log and its reported SHA-256 are the reviewable evidence.

## Evidence Layout and Claim Boundary

Fault-run directory:

- `injector_events.jsonl`: independent arming, target process/task, injection time, injector PID and host.
- `framework_runs/<run-id>/events.jsonl`: framework lifecycle, Cloud transport failure, failover, Edge completion, and controller completion.
- `cloud_worker_events.jsonl`: Cloud process and request start; the injected request must have no finish event.
- `edge_worker_events.jsonl`: local Edge records, or the copied run-specific log from B.
- `workspace/artifacts/recovered_result.json`: output with run/task/node identity and digest.
- `workspace/artifacts/final_report.json`: final deliverable with the retained intermediate artifact hash and the externally injected failure/failover decision trace.
- `summary.json`, `manifest.json`, and `acceptance_verification.json`: execution summary, source revision/dirty-tree fingerprint, file hashes, and independently reconstructed checks.

Requirement-change directory:

- `change_injector_events.jsonl` and `framework_change_events.jsonl`: external injection and framework detection.
- `inbox/change_request.json`: the exact new acceptance revision.
- `framework_runs/<run-id>/events.jsonl` and `state.json`: both phase plans and final controller state.
- `workspace/artifacts/baseline_report.json` and `revised_report.json`: original and adapted deliverables.
- `manifest.json`: run-scoped file hashes and byte counts.

The single-host run proves the framework's in-process routing/recovery path under an external process failure, followed by a separately evaluated final-delivery phase. The separate requirement-change run proves deterministic re-planning and prior-artifact retention. Both runs are fixed-agent controls; they do not establish model-generated interpretation of arbitrary user intent or requirement changes. Only a successful `--require-cross-host --require-edge-log` verification on the actual two-computer bundle supports a cross-host demonstration claim. Neither scenario establishes recovery from every possible failure or guarantees completion when the fallback node, network, or required service is unavailable.

## Legacy Evidence

The previous E1/E2/E3 package is retained unchanged. Its E2 remains a controlled fallback run from the standalone experiment script; it is not relabeled as this external injection or main-framework evidence.
