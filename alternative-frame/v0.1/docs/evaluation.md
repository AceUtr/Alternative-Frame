# 统一评测与指标说明

## 1. 目标

本模块为科研 Demo、软件工程 Demo 和端边云 Demo 提供同一套可追溯指标。所有聚合结果必须能够回溯至 `run_id`、`state.json`、`events.jsonl`、`AgentResult`、`tool_records` 或 `runs/results.jsonl`。

当前完成的是阶段 D1：指标 Schema、基础采集、兼容读取和测试。Benchmark、图表、UI 和比赛脚本在后续阶段实现。

## 2. 指标定义

| 指标 | 计算规则 | 空值规则 |
|---|---|---|
| 最终目标完成率 | `final_goal_completed=True` 的已知运行数 / 最终状态已知的运行数 | 没有已知运行时为 `null` |
| 子任务成功率 | success 子任务数 / 已执行子任务数 | 分母为 0 时为 `null` |
| 首次通过率 | success 且 `attempts == 1` 的子任务数 / 已执行子任务数 | 分母为 0 时为 `null` |
| 重试次数 | 所有任务 `max(attempts - 1, 0)` 之和 | 无任务时为 0 |
| 局部恢复次数 | `RunReport.local_recovery_cycles` 或各 `PhaseRecord.local_recovery_cycles` 之和 | 无记录时为 0 |
| 跨阶段次数 | `max(phase_count - 1, 0)` | 初始阶段不计为跨阶段 |
| 总耗时 | 运行开始至最终状态的墙钟时间 | 无法计算时为 `null`；旧接口保持浮点秒数 |
| 模型调用与 Token | 从模型响应或工具记录中的 `usage` 获取 | 未采集到为 `null`，不得写成真实 0 |
| 估算成本 | 仅在配置了明确模型价格后计算 | 无价格配置为 `null` |
| 工具调用成功率 | `success is True` 的工具记录数 / 工具记录总数 | 无工具调用时为 `null` |
| 人工干预次数 | 合同修改、暂停、人工重跑等已定义事件数 | 尚未接入事件映射时为 0，并在报告中说明 |
| 节点分布 | device/edge/cloud/unknown 的任务数 | 未提供节点字段归入 unknown |

`0`、`null`（unknown）和“不适用”不能混用。

## 3. 当前数据来源

| 数据 | 来源 | 当前状态 |
|---|---|---|
| 任务状态、重试次数 | `core/models.py` 的 `AgentResult.status/attempts` | 已接入 |
| 工具调用与成功状态 | `AgentResult.tool_records` | 已接入 |
| 单任务起止时间 | `AgentResult.started_at/finished_at` | 已接入 |
| 局部恢复次数 | `RunReport.local_recovery_cycles`、`PhaseRecord.local_recovery_cycles` | 已接入 |
| 阶段数量 | `LongHorizonState.phases` | 已接入 |
| 最终目标状态 | 普通运行 `RunReport.status`；长程运行 `LongHorizonState.status` | 已接入 |
| Token usage | 工具/模型记录中的 `usage` | 解析已支持；上游仍可能未写入 |
| 节点 device/edge/cloud | task/result metadata 或未来 C 模块字段 | Schema 已预留，当前大多为 unknown |
| 人工干预事件 | `events.jsonl` | 规则尚需与队长确认 |
| 成本 | 显式模型价格表 | 尚未配置，因此为 unknown |

## 4. Schema

`RunMetrics.schema_version` 当前为 `1.0`。核心对象：

- `TaskMetrics`：单个子任务状态、尝试次数、时延、节点和调用统计。
- `CallMetrics`：单次模型/API/工具调用统计。
- `RunMetrics`：单次运行的原始和派生指标。
- `EvaluationSummary`：多次运行的聚合结果。

写入格式为 append-only JSONL。每行是一条独立运行记录。

## 5. 兼容与安全

- 旧版没有 `schema_version` 的 `runs/results.jsonl` 可继续读取，并标记为 `0.1`。
- 坏行会被跳过，不影响其他有效记录。
- `api_key`、`authorization`、`token`、`password`、`secret` 等字段在持久化前递归替换为 `[REDACTED]`。
- 旧记录中的 Token=0 可能代表未采集，读取后通过 metadata 标记歧义。

## 6. 当前尚未完成

1. 模型客户端需要把真实响应 usage 写入可采集记录。
2. C 模块需要提供统一节点字段，建议使用 `deployment_target`，取值为 `device/edge/cloud`。
3. 人工干预事件的精确定义和映射需要队长确认。
4. 成本计算需要显式模型价格配置。
5. Benchmark Runner、CSV/JSON 汇总、图表和 UI 属于 D2-D4。

## 7. 测试

在 `alternative-frame/v0.1` 下执行：

```bash
python -m pytest tests/test_metrics.py -q
```

完整回归：

```bash
python -m pytest -q
```
