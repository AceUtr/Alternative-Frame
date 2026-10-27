# 端边云模块交接给 D 同学

日期：2026-10-27  
交接方：C（端边云）  
接收方：D（评测、基准与比赛交付）  
当前代码分支：`feature/edge-cloud-runtime`  
当前本地基线：`758715e`  

## 1. 交接目的

C 向 D 提供端边云运行产物、事件和稳定数据契约，供评测适配器、指标重算和 UI 展示使用。D 侧请按 `requirement/D-evaluation-delivery-agent-requirement.md` 独立读取原始证据并复算指标；不要只抄写 `runtime_view.json` 中的汇总值。

## 2. 当前已提供的样例

样例根目录：`examples/edge_cloud/samples/`

| 场景 | 目录 | Run ID | 场景说明 |
|---|---|---|---|
| 正常路由 | `normal/` | `sample-normal-v1` | device、edge、cloud 均有成功执行记录 |
| 云故障回退 | `cloud_edge_fallback/` | `sample-cloud-edge-fallback-v1` | cloud 执行失败，任务回退 edge 并成功 |
| 暂停恢复 | `pause_resume/` | `sample_pause_resume_v1` | 阶段 2 暂停；恢复探测确认 cloud 离线；阶段 3 的恢复任务路由到 edge，合同完成 |

暂停恢复样例包含：

```text
examples/edge_cloud/samples/pause_resume/
  README.md
  state.json
  events.jsonl
  runtime_view.json
```

其中 `state.json.run_id` 与 `runtime_view.json.run_id` 均为 `sample_pause_resume_v1`；事件日志来自同一运行。`runtime_view.json` 的 `schema_version` 为 `1.0`。该场景的关键事件包括 `node_state_reprobed`、恢复后针对 `post_resume_task` 的 edge 路由，以及最终 `run_completed`。

正常和云故障回退目录也有 `state.json`、`events.jsonl`、`runtime_view.json`。请以对应的 `run_id` 关联文件；旧固定样例中的运行状态字段可能与当前运行状态模型不同，读取时以文件实际存在字段为准。

## 3. `runtime_view.json` 数据契约

Schema 定义：`examples/edge_cloud/runtime_view.schema.json`  
字段说明：`docs/edge-cloud.md`

顶层结构保持兼容：

```json
{
  "schema_version": "1.0",
  "run_id": "one-run-id",
  "nodes": [],
  "route_events": [],
  "metrics": {}
}
```

当前稳定指标：

- `node_distribution`：每类节点最终成功完成的任务数。
- `node_duration_seconds`：每类节点所有执行尝试的累计耗时，包含失败尝试。
- `node_failure_count`：每类节点失败执行尝试数。
- `fallback_count`：按任务最大回退计数汇总的回退次数。
- `execution_attempt_count`：节点执行尝试记录总数。
- `no_eligible_node_count`：没有合格节点可执行的任务次数。

节点类型固定为 `device`、`edge`、`cloud`、`unknown`。耗时单位为秒。缺失或未知节点类型应归入 `unknown`；未采集值不要伪装为零。事件时间使用 ISO 8601。

每次节点尝试的原始记录在 `state.json` 的 `evidence_records` 中，类型为 `runtime_executor`，应至少检查 `task_id`、`node_id`、`node_type`、`success`、`duration`、`fallback_count` 和 `failure_kind`。路由细节也记录在 `events.jsonl`，包括 placement、执行开始/失败/完成、fallback 和恢复探测事件。

## 4. 请 D 侧完成的核对

1. 从每个样例的 `state.json.evidence_records` 独立重算端边云指标，并与 `runtime_view.json.metrics` 对照。
2. 验证 `state.json`、`events.jsonl`、`runtime_view.json` 的 `run_id` 对齐；发现旧样例缺字段时标记为 `unknown` 并反馈 C，不要静默补成真实值。
3. 在统一评测 Schema 中区分 `0`、`unknown` 和“不适用”。这些固定样例只能用于验证解析与展示，不应直接当成真实模型实验结果或比赛统计结论。
4. UI/评测侧只读这些原始输入，不回写 C 的样例文件，也不通过解析自然语言 `placement_reason` 重新推断聚合指标。
5. 请反馈 D 侧期望的字段缺口或兼容问题；需要改变 `schema_version` 或既有字段语义时，先由 C、D 与队长确认方案。

## 5. 复跑暂停恢复场景

从 `alternative-frame/v0.1` 目录执行，生成新的本地运行目录：

```powershell
python -c "from pathlib import Path; from run_edge_cloud_replan_demo import run_demo; paused, completed, view, run_dir = run_demo(Path('runs/edge_cloud_replan'), 'pause_resume_repro', resume_cloud_online=False); print(paused.status, completed.status, run_dir)"
```

这是单机端、边、云节点模拟。它验证当前探测、暂停恢复和路由证据格式，不代表真实多设备或跨网络部署。复跑生成的耗时会变化，不应要求与固定样例中的时间数值相同。

## 6. 验收状态与协作边界

- 本次交接补充了暂停恢复固定样例及相关说明。
- 已核对暂停恢复样例的 `run_id`、`schema_version`、完成状态和关键路由事件。
- 本次没有重跑端边云专项测试、贡献门禁或全量回归；请不要把这次交接文档视为最终验收报告。
- 当前改动尚未提交或推送 GitHub，仍在本地 `feature/edge-cloud-runtime` 工作区。
- C 负责节点、路由、回退、暂停恢复和 `runtime_view` 数据生产；D 负责统一评测、指标独立复算、对照实验和评测展示。请勿把 `GenExp`、`robin` 或 `science-sandbox` 的业务代码并入端边云模块。

## 7. 相关文件

- D 任务书：`requirement/D-evaluation-delivery-agent-requirement.md`
- 端边云说明：`docs/edge-cloud.md`
- Schema：`examples/edge_cloud/runtime_view.schema.json`
- 样例索引：`examples/edge_cloud/README.md`
- 暂停恢复样例：`examples/edge_cloud/samples/pause_resume/`

