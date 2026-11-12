# Dynamic Fault and Requirement-Change Acceptance

This acceptance adds two independently injected runtime scenarios to the main `AgentRegistry` → `Orchestrator` → `LongHorizonController` path:

1. A separate process waits until the Cloud worker has started a specific task, then terminates that worker. The controller must detect the transport failure, retry the same task on Edge, continue the dependent artifact task, and finish without a human pause or resume.
2. A separate process waits until the baseline artifact is complete, then writes a new acceptance criterion into the run-scoped inbox. The controller detects the change, produces a second-phase plan, preserves the baseline artifact, and satisfies the added criterion.

Neither worker has an internal fault-mode flag. The injected event is not passed into the controller. The demo exercises deterministic digest and report agents; it does not prove model-generated interpretation, provider resilience, or production availability.

The official PDF was not present in this workspace at the time of implementation. The quoted clause and scenario interpretation therefore follow `动态异常注入改造任务书_交Codex.md`; before making an official compliance claim, compare the wording with the organizer's original competition document.

## Local Process-Fault Control

From `alternative-frame/v1.1-experimental`, run:

```powershell
python -m core.edge_cloud.demo --evidence-dir runs/dynamic_fault_injection --inject-delay-seconds 0.8 --cloud-delay-seconds 5 --cloud-timeout-seconds 2.5
```

The independent injector waits for `worker_task_started` for `remote_digest`, waits the configured interval, then terminates the Cloud PID recorded by the worker. This is a same-computer loopback control, not a multi-device result.

The runner exits nonzero unless its execution checks pass. Verify the saved raw evidence separately:

```powershell
python -m core.edge_cloud.evidence runs/dynamic_fault_injection/<run-id> --output runs/dynamic_fault_injection/<run-id>/acceptance_verification.json
```

The verifier reconstructs run/task identity and event ordering, checks that Cloud started but did not finish the task, checks the same task failed over and completed on Edge, audits controller and artifact state, and verifies manifest size/hash records. The output warns when both nodes have the same host identity.

## Dynamic Requirement-Change Control

Run the separate mid-run requirement-change scenario:

```powershell
python -m core.long_horizon.dynamic_change_demo --evidence-dir runs/dynamic_requirement_change
```

The external injector waits for successful creation of `baseline_report.json`, then atomically publishes revision 2 of the acceptance request. The inbox monitor records detection. `LongHorizonController` must schedule phase 2, write `revised_report.json`, and leave the original baseline byte-for-byte unchanged.

Run the independent verifier:

```powershell
python -m core.long_horizon.dynamic_change_demo --verify-run runs/dynamic_requirement_change/<run-id> --output runs/dynamic_requirement_change/<run-id>/acceptance_verification.json
```

This is a deterministic local control for dynamic requirement updates. It does not claim that an LLM understood an arbitrary natural-language change.

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
python -m core.edge_cloud.evidence runs/dynamic_fault_injection/<run-id> --require-edge-log --require-cross-host --output runs/dynamic_fault_injection/<run-id>/acceptance_verification.json
```

The final check requires matching run/task IDs, Cloud and Edge event records, different hostnames and hashed host fingerprints, and intact evidence hashes. A successful HTTP request to a LAN address alone is not a two-computer acceptance. The verifier's result plus the copied Edge log and its reported SHA-256 are the reviewable evidence.

## Evidence Layout and Claim Boundary

Fault-run directory:

- `injector_events.jsonl`: independent arming, target process/task, injection time, injector PID and host.
- `framework_runs/<run-id>/events.jsonl`: framework lifecycle, Cloud transport failure, failover, Edge completion, and controller completion.
- `cloud_worker_events.jsonl`: Cloud process and request start; the injected request must have no finish event.
- `edge_worker_events.jsonl`: local Edge records, or the copied run-specific log from B.
- `workspace/artifacts/recovered_result.json`: output with run/task/node identity and digest.
- `summary.json`, `manifest.json`, and `acceptance_verification.json`: execution summary, source revision/dirty-tree fingerprint, file hashes, and independently reconstructed checks.

Requirement-change directory:

- `change_injector_events.jsonl` and `framework_change_events.jsonl`: external injection and framework detection.
- `inbox/change_request.json`: the exact new acceptance revision.
- `framework_runs/<run-id>/events.jsonl` and `state.json`: both phase plans and final controller state.
- `workspace/artifacts/baseline_report.json` and `revised_report.json`: original and adapted deliverables.
- `manifest.json`: run-scoped file hashes and byte counts.

The single-host run proves the framework's in-process routing/recovery path under an external process failure. The separate requirement-change run proves deterministic re-planning and prior-artifact retention. Only a successful `--require-cross-host --require-edge-log` verification on the actual two-computer bundle supports a cross-host demonstration claim. Neither scenario establishes recovery from every possible failure or guarantees completion when the fallback node, network, or required service is unavailable.

## Legacy Evidence

The previous E1/E2/E3 package is retained unchanged. Its E2 remains a controlled fallback run from the standalone experiment script; it is not relabeled as this external injection or main-framework evidence.
