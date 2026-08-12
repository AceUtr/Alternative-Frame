# 端边云协同运行时 v0.2

## 目标与接入位置

本模块在单机上模拟 `device`、`edge`、`cloud` 三类执行节点，为长程任务提供可解释的放置、执行事件、动态故障和合规回退。它不宣称已经完成真实设备或远程云部署。

```text
SubTask.metadata
  -> TaskRequirements
  -> NodeRouter
  -> RuntimeExecutor
  -> AgentResult.tool_records
  -> LongHorizonState.evidence_records
```

`NodeRoutedAgent` 包装现有 Agent，使用 `SubTask.metadata` 这个既有扩展点接入路由。核心 `Orchestrator`、`LongHorizonController`、`Plan`、`SubTask` 和 `AgentResult` 的接口均未修改。

## 长程科研 Demo

运行：

```powershell
python run_edge_cloud_long_horizon_demo.py
```

Demo 执行四个有依赖关系的真实文件任务：

1. 敏感测量数据去标识和归一化，只能放在 `device`。
2. 匿名数据普通推理，优先放在 `edge`。
3. 高算力参数实验，优先放在 `cloud`。
4. 后续云实验注入节点离线，自动回退到 `edge`。

每次运行生成：

```text
runs/edge_cloud_long_horizon/<run_id>/
  state.json
  events.jsonl
  runtime_view.json
  workspace/artifacts/*.json
```

`runtime_view.json` 是可直接 `json.load` 的 UI 输入；本阶段没有修改 `ui.py`。稳定 schema 和固定样例位于：

- `examples/edge_cloud/runtime_view.schema.json`
- `examples/edge_cloud/runtime_view_normal.json`
- `examples/edge_cloud/runtime_view_cloud_edge_fallback.json`
- `examples/edge_cloud/samples/normal/`
- `examples/edge_cloud/samples/cloud_edge_fallback/`

后两个目录是交给 D 的固定演示输入，每个目录包含同一 `run_id` 对齐的 `state.json`、`events.jsonl` 和 `runtime_view.json`。

三类文件必须使用同一个 `run_id` 对齐。UI 或 benchmark 只能读取 `state.json`、`events.jsonl`、`runtime_view.json`，不得回写原始文件。
新生成的 v1.0 数据总是带 `run_id`；为兼容第二阶段已经生成的 v1.0 文件，读取端应允许该字段缺失，并将其标记为 `unknown` 或从对应 `state.json` 补齐。

## 运行事件与 evidence

`LongHorizonEventSink` 将以下事件追加到该 run 的 `events.jsonl`：

- `placement_decided`
- `node_execution_started`
- `node_execution_failed`
- `node_fallback_started`
- `node_execution_completed`

每次节点执行尝试都会写入 `AgentResult.tool_records`，随后由现有长程控制器自动保存到 `state.json` 的 `evidence_records`。节点记录稳定包含：

- `node_id`
- `node_type`
- `placement_reason`
- `duration`（秒）
- `fallback_count`

同时保留 `actual_duration_ms`、`failure_kind`、`task_id` 和 `success`，便于诊断。

## 与 D 成员的数据约定

运行时指标结构版本为 `schema_version = "1.0"`，由 `aggregate_runtime_metrics(evidence_records)` 产生：

| 字段 | 类型 | 语义 |
|---|---|---|
| `node_distribution` | `object<string,int>` | 各 node_type 最终成功完成的任务数 |
| `node_duration_seconds` | `object<string,float>` | 各 node_type 所有执行尝试的累计秒数，包含失败尝试 |
| `node_failure_count` | `object<string,int>` | 各 node_type 失败执行尝试数 |
| `fallback_count` | `int` | 每个任务最大 fallback_count 的总和 |
| `execution_attempt_count` | `int` | 节点执行尝试记录总数 |
| `no_eligible_node_count` | `int` | 没有合格节点的任务次数 |

节点类型键固定为 `device`、`edge`、`cloud`、`unknown`。时间统一使用秒，事件时间使用 ISO 8601。D 的 UI/评估模块应读取上述聚合字段，不需要解析自然语言 `placement_reason`。

`build_runtime_view(nodes, evidence_records, events).to_dict()` 返回：

```json
{
  "schema_version": "1.0",
  "run_id": "one-run-id",
  "nodes": [],
  "route_events": [],
  "metrics": {}
}
```

缺失或未知的 `node_type` 必须累计到 `unknown`，不能默认为 `device` 或数值 `0`。聚合指标必须能够从 `state.json` 中原始 `runtime_executor` records 重新计算并与 `runtime_view.json.metrics` 一致。

## 跨阶段 Replan 与恢复

运行：

```powershell
python run_edge_cloud_replan_demo.py
```

该演示现在由正式 `AcceptanceContract` 驱动。第一阶段只完成敏感数据 device 预处理，全局评估明确输出剩余 `missing_criteria`；`contract_replan` 只根据这些缺口生成后续路由任务，不读取阶段编号。只有以下 required 条款全部具有当前 run 证据时才会完成：

- `device_sensitive_preprocess`
- `high_compute_artifact`
- `cloud_edge_fallback_evidence`
- `post_resume_task_completed`
- `final_report_exists`

第二阶段完成 cloud 故障与 edge 回退后在阶段边界暂停。恢复时使用一组全新的节点对象，并通过 current probe 获取实时状态。历史 `node_state.json` 只用于审计和差异比较，不再覆盖当前探测。

`NodeStateStore` sidecar 保存 `node_id`、`node_type`、`online`、`network_available` 和 `probe_status`，不修改冻结的 `LongHorizonState` 数据模型。恢复探测会产生：

- `node_state_snapshot_saved`
- `node_state_reprobed`
- `node_state_changed`（仅状态确实变化时）

探测失败或没有有效探测时状态为 `unknown`，节点不会被当作在线候选。恢复时 cloud 重新上线可再次选 cloud；恢复时 cloud 离线则选择 edge。

## 动态故障语义

- `offline` -> `failure_kind=node_offline`
- `network` -> `failure_kind=network_interrupted`
- `timeout` -> `failure_kind=timeout`
- 无节点满足硬约束 -> `failure_kind=no_eligible_node`

只有节点执行异常会触发跨节点回退。Agent/工具业务异常不跨节点重复执行，仍交给现有 Orchestrator 的任务级重试，避免重复非幂等副作用。敏感任务即使失败，也只能在合格的 device 节点之间回退。

## 验证

```powershell
python -m pytest tests/test_node_routing.py tests/test_runtime_fallback.py tests/test_runtime_dynamic_state.py tests/test_edge_cloud_long_horizon.py -q -p no:cacheprovider
python validate_contribution.py --runtime edge-cloud --no-report
```

未来接真实节点时，可在 `ExecutionNode.execute()` 后增加 HTTP/gRPC 适配器，但需要另行完成身份认证、传输加密、命令白名单、超时、幂等、日志脱敏和产物传输。
