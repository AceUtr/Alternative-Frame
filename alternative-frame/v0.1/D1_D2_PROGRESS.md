# D1 / D2 实现进度

## 指标审计

| 指标 | 当前状态 | 数据来源 | 说明 |
|---|---|---|---|
| 最终目标完成率 | 已支持 | `RunReport.status` / `LongHorizonState.status` | 聚合时仅对已知 completion 状态计算 |
| 子任务成功率 | 已支持 | `AgentResult.status` | `success / 已执行任务数` |
| 首次通过率 | 已支持 | `AgentResult.attempts + status` | success 且 attempts=1 |
| 重试次数 | 已支持 | `AgentResult.attempts` | `sum(max(attempts-1, 0))` |
| 局部恢复次数 | 已支持 | `RunReport.local_recovery_cycles` / `PhaseRecord.local_recovery_cycles` | 长任务按 phase 求和 |
| 跨阶段次数 | 已支持 | `LongHorizonState.phases` | `phase_count` 和 `additional_phase_count` 分开记录 |
| 总耗时 | 已支持 | report wall clock / state created_at~updated_at | 单阶段 runner 用 perf_counter |
| 模型调用数 | 部分支持 | `AgentResult.evidence` | 依赖现有 evidence 标记；真实样例到位后校准 |
| Token | 部分支持 | `tool_records.usage` / `metadata.usage` | 缺失时为 `None/unknown`，不写 0 |
| 估算成本 | 已支持框架 | 显式 pricing config + Token | 无价格配置时 unknown |
| 工具调用成功率 | 已支持并修正 | `AgentResult.tool_records` | 无 usage 的工具调用也会进入 calls |
| 人工干预次数 | 已支持框架 | `events.jsonl` | 已定义 pause/contract edit/manual rerun 等事件；待真实事件名校准 |
| 节点任务分布 | 已支持 | task/result metadata | device/edge/cloud/unknown |
| 节点失败数 | 新增支持 | TaskMetrics | 每节点失败任务数 |
| 节点耗时 | 新增支持 | AgentResult started_at/finished_at | 每节点累计已知耗时；无数据为 unknown |

## D1 已完成

- `RunMetrics` schema 升级到 `1.1`，旧 `0.1` JSONL 保持兼容读取。
- 保留 `0` 与 `unknown(None)` 的语义差异。
- 修复原实现中无 Token usage 的工具调用不会进入 `calls` 的问题。
- 修复 `metrics_from_report()` 未真正使用 Plan metadata 获取执行节点的问题。
- 增加显式模型价格配置的成本估算。
- 增加 `events.jsonl` 容错读取和人工干预事件统计。
- 增加节点任务数、失败数、累计耗时。
- JSONL 保持 append-only；坏行跳过；敏感字段递归脱敏。

## D2 已完成

新增：

- `run_benchmarks.py`
- `benchmarks/configs/smoke.json`
- `benchmarks/results/raw/`
- `benchmarks/results/summary/`
- `benchmarks/workspaces/`
- `tests/test_benchmark_runner.py`

Runner 当前支持：

- `BenchmarkConfig` / `BenchmarkCase`；
- task、mode、repeats、budget、model、seed、max_workers、fixture、pricing；
- 每个样本独立 workspace；
- fixture 重置和隔离；
- 单个样本异常后继续下一样本；
- 原始 JSONL append-only 输出；
- 汇总 JSON + CSV；
- 汇总结果可由 raw JSONL 重算验证；
- smoke runner 明确标记为 `stub_pipeline_validation`，不可作为比赛最终结论。

## 测试

D 专项：

```text
python -m pytest tests/test_metrics.py tests/test_benchmark_runner.py -q
14 passed
```

Smoke：

```text
python run_benchmarks.py --config benchmarks/configs/smoke.json
```

已成功生成 raw JSONL、summary JSON 和 summary CSV。

全项目测试仍有 2 个原仓库既有失败；在未修改原仓库副本中可复现同样两个失败，因此不是本次 D1/D2 修改引入：

1. `tests/test_global_evaluator.py` 缺少 `GoalEvaluation` 名称导入。
2. `tests/test_structured_replanner.py` 期望事件序列没有 `replan_retry_wait`，但当前业务实现会发出该事件。

## 下一步待真实数据校准

- model usage 的真实记录位置和字段名；
- C 模块 node metadata 的最终字段名；
- 人工干预事件的正式 event 名；
- 真实模型价格表与比赛预算口径；
- 单 Agent vs 多 Agent 的正式业务实现入口（当前 smoke 仅验证 serial vs parallel 统计管线，不用于最终对照结论）。
