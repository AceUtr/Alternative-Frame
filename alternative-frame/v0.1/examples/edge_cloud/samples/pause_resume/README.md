# Pause and Resume Sample

Run ID: `sample_pause_resume_v1`

The run pauses after phase 2, after the cloud attempt fails and execution falls
back to edge. On resume, a current probe confirms cloud is still offline. The
post-resume task and final report run on edge, and the acceptance contract
completes in phase 3.

Files:

- `state.json`: persisted contract, phase, task, and execution evidence.
- `events.jsonl`: pause/resume, node probe, placement, and execution events.
- `runtime_view.json`: schema 1.0 view aligned to the same run ID.

This is a single-machine simulation. It does not represent deployment across
real devices or networks.
