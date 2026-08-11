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

`runtime_view.json` 是可直接 `json.load` 的 UI 输入；本阶段没有修改 `ui.py`。

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
  "nodes": [],
  "route_events": [],
  "metrics": {}
}
```

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
