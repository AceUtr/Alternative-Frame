# C 成员：端边云第三阶段开发与验收任务书

## 1. 当前基线

当前远程分支：`feature/edge-cloud-runtime`

审核基线提交：

```text
cdd0cee feat(runtime): integrate edge-cloud long-horizon demo
```

队长独立审核结果：

```text
python validate_contribution.py --runtime edge-cloud --no-report  passed
端边云专项测试                                           17 passed
run_edge_cloud_long_horizon_demo.py                     completed
git diff --check                                        passed
完整测试                                                103 passed, 2 failed
```

完整测试中的两个失败来自当前公共基线中的既有问题：

1. `tests/test_global_evaluator.py` 缺少 `GoalEvaluation` 导入；
2. `tests/test_structured_replanner.py` 的预期事件未包含 `replan_retry_wait`。

端边云分支没有修改对应核心模块，因此不要在本分支擅自修复这两个公共问题，交由队长在集成分支统一处理。

## 2. 已完成能力

以下能力已经通过审核，不要重复重写：

- `ExecutionNode`、`DeviceNode`、`EdgeNode`、`CloudNode`；
- `TaskRequirements`、`PlacementDecision`、`NodeRouter`；
- 隐私、能力、网络、时延、成本、在线状态硬约束；
- 确定性节点评分和候选排序；
- `RuntimeExecutor` 节点执行与合规回退；
- `NodeRoutedAgent` 对现有 Agent 的兼容包装；
- 节点离线、网络中断、超时、无合格节点测试；
- 四任务科研端边云长程 DAG；
- `state.json`、`events.jsonl` 和 `runtime_view.json`；
- 五类路由事件持久化；
- 节点分布、耗时、失败数和回退数聚合指标。

当前 Demo 已真实验证：

```text
敏感数据预处理  -> device
匿名数据推理    -> edge
高算力实验      -> cloud
云节点故障      -> cloud 失败后回退 edge
```

## 3. 第三阶段目标

本阶段要把“单阶段 DAG 内的节点路由与回退”升级为：

1. 跨阶段 Replan 后的新任务仍经过端边云路由；
2. 暂停和恢复后节点状态及路由行为可解释、可复现；
3. D 成员可以稳定消费端边云指标；
4. 队长可以直接把 `runtime_view.json` 接入 UI；
5. 可选增加一个受控 HTTP EdgeNode，证明节点接口可替换为远程执行。

本阶段不要求构建完整真实分布式平台，也不允许通过 SSH 或任意远程命令执行来冒充端边云协同。

## 4. 必须完成：跨阶段端边云任务

新增一个明确的两阶段场景：

```text
阶段 1：
  device 完成敏感数据预处理
  edge 完成匿名数据推理

全局合同验收：
  发现缺少高算力实验、独立验证或最终报告

阶段 2：
  Replanner 根据缺失合同条款生成后续任务
  新任务必须再次经过 NodeRouter
  优先在 cloud 执行
  cloud 故障时回退 edge，或在不适合回退时由长程控制器继续 Replan

最终合同验收：
  所有 required 条款具有当前运行证据后才能 completed
```

必须证明以下区别：

- `node fallback`：同一个任务从 cloud 换到 edge；
- `task retry`：同一个 Agent 根据反馈重新执行；
- `local DAG recovery`：只恢复失败节点及下游；
- `cross-phase replan`：新增阶段补齐合同缺口。

禁止把这四种机制混为同一个计数。

建议新增：

```text
run_edge_cloud_two_phase_demo.py
tests/test_edge_cloud_two_phase.py
```

## 5. 必须完成：暂停与恢复语义

为节点状态建立明确的恢复规则，并写入文档：

### 方案要求

- 保存上次路由时看到的节点快照；
- 恢复运行时明确区分：
  - `persisted_snapshot`：历史节点状态；
  - `current_probe`：恢复时重新探测的当前节点状态；
- 实际路由默认使用 `current_probe`；
- 历史快照只用于审计和对比，不能覆盖真实当前状态；
- 如果当前无法探测，必须标为 `unknown`，不能自动当作在线；
- 节点状态变化应写入 `events.jsonl`。

至少新增以下事件之一：

```text
node_state_snapshot_saved
node_state_reprobed
node_state_changed
```

至少测试：

1. 暂停前 cloud 在线，恢复后 cloud 离线，应重新路由到 edge；
2. 暂停前 cloud 离线，恢复后恢复在线，可以重新选择 cloud；
3. 无法探测节点时不能伪造 `online=True`；
4. 恢复后不得重复执行已经冻结且成功的无关任务。

## 6. 必须冻结的数据合同

C 成员负责生产原始数据，D 成员负责消费。未经队长确认，不得随意修改以下字段语义。

### 6.1 文件关联

同一次运行必须通过同一个 `run_id` 关联：

```text
state.json
events.jsonl
runtime_view.json
workspace/artifacts/*
```

### 6.2 runtime_view.json

当前 schema：

```json
{
  "schema_version": "1.0",
  "nodes": [],
  "route_events": [],
  "metrics": {}
}
```

必须稳定提供：

```text
node_distribution
node_duration_seconds
node_failure_count
fallback_count
execution_attempt_count
no_eligible_node_count
```

节点类型键固定为：

```text
device
edge
cloud
unknown
```

缺失值必须使用 `null` 或明确的 `unknown` 语义，不得把未采集数据自动记为 0。

### 6.3 runtime_executor 记录

每次节点执行尝试至少包含：

```text
task_id
node_id
node_type
success
placement_reason
duration
fallback_count
failure_kind
```

建议同时保留：

```text
estimated_latency_ms
estimated_cost
actual_duration_ms
candidate_scores
rejected_nodes
```

### 6.4 路由事件

继续保持：

```text
placement_decided
node_execution_started
node_execution_failed
node_fallback_started
node_execution_completed
```

事件必须包含 `task_id`，节点事件必须包含 `node_id` 和 `node_type`。

## 7. 与 D 成员的协作方式

C 成员向 D 成员提供：

1. 一次无故障正常路由样例；
2. 一次 `cloud -> edge` 回退样例；
3. 一次跨阶段 Replan 样例；
4. 每个样例对应的完整运行目录；
5. 字段说明和 `schema_version`；
6. 用于重新计算指标的测试或示例代码。

D 成员负责：

- 只读取原始文件，不修改 C 产生的数据；
- 将端边云指标映射到统一 `RunMetrics`；
- 从原始 `runtime_executor` 记录重新计算聚合结果；
- 比较固定节点与动态路由；
- 将缺失数据标记为 `unknown`；
- 输出 raw JSONL、summary JSON/CSV 和图表。

C、D 共同验收：

```text
runtime_view.metrics
== D 根据 state.evidence_records 重新计算的结果
```

如果不相等，不能进入最终报告。

## 8. UI 数据适配要求

本阶段不要直接重写 `ui.py`。队长负责最终 UI 接线。

C 成员只需要保证 `runtime_view.json` 可以直接 `json.load()`，并提供以下内容：

- 节点列表和健康状态；
- 任务路由时间线；
- cloud 失败到 edge 回退的顺序；
- 每类节点任务数、耗时和失败数；
- schema 版本；
- 一份固定的 UI 展示样例。

不要在渲染层重新计算指标，不要把自然语言日志作为唯一数据源。

## 9. 可选加分项：受控 HTTP EdgeNode

只有前述必做项全部通过后，才考虑实现。

允许实现：

```text
Harness
  -> HTTP JSON 请求
  -> 受控 edge service
  -> 结构化结果
```

必须具备：

- 固定动作白名单；
- 请求超时；
- 明确身份或测试凭据；
- 日志脱敏；
- 幂等或请求 ID；
- 不允许执行用户提供的任意 shell 命令；
- 离线本地回退方案。

这只是证明 `ExecutionNode` 可替换，不要求搭建真实手机和公有云集群。

## 10. 修改边界

允许修改：

```text
core/runtime_nodes/
core/routing/
examples/edge_cloud/
run_edge_cloud_demo.py
run_edge_cloud_long_horizon_demo.py
新增端边云入口脚本
tests/test_node_routing.py
tests/test_runtime_fallback.py
tests/test_runtime_dynamic_state.py
tests/test_edge_cloud_long_horizon.py
新增端边云测试
docs/edge-cloud.md
validation/manifests/edge-cloud.json
```

未经队长批准，不得修改：

```text
core/models.py
core/orchestrator.py
core/long_horizon/controller.py
core/long_horizon/state.py
core/acceptance.py
ui.py
科研 Demo 业务文件
软件 Demo 业务文件
```

冻结接口：

```text
SubTask
Plan
AgentResult
AcceptanceContract
Agent.run()
Tool.execute()
```

扩展信息继续使用 `SubTask.metadata`、`AgentResult.tool_records` 和独立的 runtime schema。

## 11. 验收命令

必须在干净工作区执行：

```powershell
python validate_contribution.py --runtime edge-cloud --no-report
python -m pytest tests/test_node_routing.py tests/test_runtime_fallback.py tests/test_runtime_dynamic_state.py tests/test_edge_cloud_long_horizon.py tests/test_edge_cloud_two_phase.py -q -p no:cacheprovider
python run_edge_cloud_demo.py
python run_edge_cloud_long_horizon_demo.py
python run_edge_cloud_two_phase_demo.py
python -m pytest -q -p no:cacheprovider
git diff --check
git status --short --branch
```

如果新增暂停恢复专项测试，也必须加入端边云 manifest。

完整测试中若仍存在公共基线的已知失败，需要列出精确测试名和错误，并证明本分支没有修改对应实现；不得只写“与我无关”。

## 12. 完成标准

第三阶段完成时必须同时满足：

- 跨阶段新任务真实经过 NodeRouter；
- 最终合同因第一阶段证据不足而拒绝，并在后续阶段通过；
- cloud 故障和回退事件可追溯；
- 暂停恢复后的节点状态语义明确且有测试；
- `state.json`、`events.jsonl`、`runtime_view.json` 使用同一 run_id；
- D 成员能够从原始记录重新计算相同指标；
- UI 数据无需自然语言解析；
- 端边云专项和贡献门禁通过；
- 不泄露凭据和个人路径；
- Git 状态干净；
- 不修改冻结核心接口。

## 13. 汇报格式

完成后按以下格式汇报：

```text
当前分支与提交：
本次完成：
修改文件：
跨阶段流程：
暂停恢复规则：
新增事件与 schema 变化：
提供给 D 的样例 run_id：
测试和门禁结果：
Smoke 运行结果：
生成产物：
未完成事项与限制：
是否修改冻结接口：
需要队长确认或集成的内容：
```

必须准确声明当前节点是单机模拟还是受控 HTTP 节点，不得将本地模拟描述为真实分布式端边云部署。
