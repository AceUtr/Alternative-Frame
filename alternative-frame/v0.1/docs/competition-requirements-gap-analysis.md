# Competition Requirements Gap Analysis

Source: `XH-202631 荣耀终端股份有限公司：面向超长程复杂任务的动态异构群体智能架构与深度协同推理技术比赛方案`.

## Requirement Mapping

| Competition requirement | Current evidence | Status | Boundary |
|---|---|---|---|
| Long-horizon task planning, execution and evaluation | `LongHorizonController`, contract planner, global evaluator, real two-phase run | Implemented | Demonstrated on controlled tasks; not arbitrary industrial tasks |
| Dynamic heterogeneous Agent communication | `TopKCommunicationRouter`, structured routing decisions and reasons | MVP implemented | Centralized sparse routing, not learned/decentralized communication |
| Device-edge-cloud heterogeneous resources | `core/runtime_nodes`, `NodeRouter`, fallback telemetry and runtime view | Controlled simulation implemented | Single-machine simulation, not physical distributed deployment |
| Fault tolerance and recovery | Task retry, phase replanning, local DAG recovery, edge fallback, six-case matrix | Implemented for controlled faults | Does not claim recovery from every external failure |
| Two high-completion cross-domain tasks | Research and Software Demo, each stable 3/3 runs | Implemented | Offline deterministic demos; real-model evidence is a separate two-phase calculator task |
| Reproducibility and system implementation | `requirements-dev.txt`, clean clone, 235 tests, four gates | Implemented | Windows Python/Tkinter prerequisite must be stated |
| Algorithm pseudocode / reproducibility explanation | Architecture, milestone and original-contribution documents | Partially implemented | Final submission PDF should include a concise algorithm/pseudocode section |
| Display task trajectories and intermediate states | UI DAG, evidence, events, runtime view, `memory.json` | Implemented in code | Requires manual final click-through and recording |
| Token/resource efficiency | Metrics schema and unknown-safe aggregation | Partially implemented | CCswitch response omitted `usage`; live token count remains unknown |

## Current Technical Gaps

1. The current Top-k communication is a bounded deterministic MVP. It should be described as dynamic sparse routing, not a fully learned dynamic topology.
2. The edge-cloud module demonstrates placement and fallback semantics on one machine; it is not evidence of physical network latency or multi-device deployment.
3. The real-model long-horizon run completed, but its provider did not return a `usage` object. Do not put a fabricated Token number in the submission.
4. The three-layer memory is now persisted by the controller, but the final UI still needs a manual check that memory/trajectory evidence is understandable to judges.

## Submission Materials From The Notice

The notice distinguishes two stages:

### Registration stage

- Register/login through the challenge website.
- Complete team and project information.
- Upload the stamped registration form PDF as required by the system.

### Product submission stage

The notice states that selected teams submit the latest product package before **2026-09-15**. It describes sending a compressed product package by email to `gengxinwei@honor.com`, with the filename containing school, team, product name and contact phone. The package should include the runnable system, source, documentation and required supporting materials.

The notice does **not** explicitly list PPT as a mandatory upload in the product-submission section. Nevertheless, prepare PPT/video/demo materials because the scoring includes system display, usability and cross-domain demonstrations, and later expert review may request them.

## Recommended Package Contents

```text
Alternative-Frame-<school>-<team>-<product>-<phone>.zip
  README.md
  requirements.txt
  requirements-dev.txt
  alternative-frame/v0.1/  (source and runnable demos)
  docs/competition-requirements-gap-analysis.md
  docs/architecture-final.md
  docs/original-contributions.md
  reports/final-evaluation-summary.md
  reports/demo-stability/summary.md
  reports/fault-matrix/fault_matrix.md
  evidence/                (selected state/events/artifacts, no API keys)
  demo/                    (run script and manual operation guide)
  presentation/            (PPT/video, recommended even if not explicitly mandatory)
```

Never include API keys, CCswitch database files, local user paths, virtual environments or large transient run directories.
