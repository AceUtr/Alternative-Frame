# C 成员：端边云最终冻结任务书

## 1. 冻结目标

当前审核基线：

```text
分支：feature/edge-cloud-runtime
提交：4606cfb feat(runtime): add routed replan and resume contract
```

已独立通过：

```text
端边云贡献门禁：passed
端边云专项测试：24 passed
跨阶段 smoke：completed
git diff --check：passed
```

已经具备：三阶段 Replan、cloud 到 edge 回退、阶段边界暂停恢复、`node_state.json`、`runtime_view.json`、D 成员固定样例和指标重算测试。

本轮只完成下面两个 P0，完成后停止新增功能并申请最终冻结。

## 2. P0-1：改为验收合同缺口驱动 Replan

当前问题：跨阶段 Demo 的 `acceptance_contract` 为 `null`，评估逻辑主要依据阶段编号，不能证明合同驱动的最终完成判断。

必须改为：

```text
AcceptanceContract
  -> 第一阶段执行
  -> GlobalEvaluator 检查合同
  -> 输出明确 missing_criteria
  -> Replanner 根据 missing_criteria 生成下一阶段任务
  -> 所有 required 条款具有当前运行证据
  -> completed
```

合同至少包含：

1. 敏感数据预处理必须在 device 完成；
2. 高算力实验必须产生可验证产物；
3. cloud 故障及回退链必须有运行证据；
4. 恢复后的任务必须完成；
5. 最终报告或汇总产物存在。

要求：

- `state.json.acceptance_contract` 不得为 `null`；
- 第一阶段的 `last_evaluation.completed` 必须为 `false`；
- `missing_criteria` 必须非空且对应合同条款；
- Replanner 不得只根据 `state.phase` 硬编码下一任务；
- 最终完成必须来自 required 条款全部通过；
- 每个文件条款必须有当前 run 的 artifact provenance；
- 每个路由条款必须有 `runtime_executor` 或路由事件证据。

建议新增或更新测试：

```text
test_first_phase_is_rejected_by_contract
test_replanner_maps_missing_criteria_to_routed_tasks
test_final_completion_requires_all_contract_evidence
test_stale_artifact_cannot_complete_contract
```

## 3. P0-2：恢复时重新探测节点状态

当前问题：`NodeStateStore.restore()` 直接用历史快照覆盖新节点状态。它能延续故障，但不能反映恢复时 cloud 已重新上线或新近离线。

必须区分：

```text
persisted_snapshot：暂停前保存的历史状态，仅用于审计
current_probe：恢复时得到的当前状态，用于实际路由
```

默认规则：

- 实际路由以 `current_probe` 为准；
- 历史快照不能覆盖有效的当前探测；
- 无法探测时状态为 `unknown`，不得默认在线；
- 记录历史状态与当前状态差异；
- 不得修改冻结的 `LongHorizonState` 字段，可继续使用 sidecar 文件。

必须新增事件：

```text
node_state_snapshot_saved
node_state_reprobed
node_state_changed
```

事件至少包含：

```text
run_id
node_id
node_type
previous_online
current_online
previous_network_available
current_network_available
probe_status
```

必须测试：

1. 暂停前 cloud 在线，恢复时离线，应选择 edge；
2. 暂停前 cloud 离线，恢复时重新上线，应允许选择 cloud；
3. 探测失败时标记 `unknown`，不能当作在线；
4. 状态未变化时不应生成虚假的 changed 事件；
5. 恢复后不重复执行已经成功并冻结的无关任务。

## 4. 数据合同冻结

保持 `runtime_view.json` schema v1.0 向后兼容：

```json
{
  "schema_version": "1.0",
  "run_id": "one-run-id",
  "nodes": [],
  "route_events": [],
  "metrics": {}
}
```

继续稳定提供：

```text
node_distribution
node_duration_seconds
node_failure_count
fallback_count
execution_attempt_count
no_eligible_node_count
```

新增节点探测事件可以进入 `route_events`，但不得改变已有字段语义。若必须升级 schema，先向队长和 D 成员提交兼容方案；本轮优先保持 v1.0。

D 成员必须能从 `state.json.evidence_records` 重新计算出与 `runtime_view.metrics` 完全一致的结果。

## 5. UI 对接边界

队长已在主 UI 增加 `runtime_view.json` 的只读展示入口。C 成员本轮：

- 不修改 `ui.py`；
- 保证输出能通过 `json.load()`；
- 保证 nodes、route_events、metrics 字段稳定；
- 提供一份最终正常样例和一份故障恢复样例；
- 所有样例使用同一组文件内一致的 `run_id`；
- 不在样例中写个人绝对路径、凭据或请求头。

## 6. 禁止事项

本轮禁止：

- 实现 HTTP/gRPC EdgeNode；
- 扩展新的路由算法；
- 重写 UI；
- 修改科研或软件 Demo；
- 修改 `SubTask`、`Plan`、`AgentResult`、`AcceptanceContract` 字段；
- 修改 `Orchestrator` 和 `LongHorizonController` 的公共语义；
- 使用阶段编号冒充合同驱动 Replan；
- 使用历史快照冒充当前节点探测。

## 7. 允许修改范围

```text
core/runtime_nodes/
core/routing/
run_edge_cloud_replan_demo.py
端边云专用入口脚本
examples/edge_cloud/
tests/test_edge_cloud_*.py
tests/test_runtime_*.py
docs/edge-cloud.md
validation/manifests/edge-cloud.json
```

需要修改范围外文件时必须先向队长说明原因。

## 8. 最终验收命令

```powershell
python validate_contribution.py --runtime edge-cloud --no-report
python -m pytest tests/test_node_routing.py tests/test_runtime_fallback.py tests/test_runtime_dynamic_state.py tests/test_edge_cloud_long_horizon.py tests/test_edge_cloud_replan_resume.py tests/test_runtime_contract.py -q -p no:cacheprovider
python run_edge_cloud_demo.py
python run_edge_cloud_long_horizon_demo.py
python run_edge_cloud_replan_demo.py
python -m pytest -q -p no:cacheprovider
git diff --check
git status --short --branch
```

将新增的合同和节点探测测试加入贡献 manifest。

## 9. 冻结判定标准

同时满足以下条件才可冻结：

- 端边云贡献门禁通过；
- 所有端边云专项通过；
- 三个端边云入口运行成功；
- `acceptance_contract` 已持久化；
- 第一阶段有真实 `missing_criteria`；
- 后续阶段由合同缺口驱动；
- 最终 required 合同条款全部通过；
- 节点恢复使用 current probe；
- 三类节点状态事件完整；
- D 可重新计算相同指标；
- UI 可以读取最终 `runtime_view.json`；
- 敏感信息扫描通过；
- `git diff --check` 无输出；
- `git status` 干净；
- 未修改冻结接口。

满足后提交：

```text
feat(edge-cloud): finalize contract-driven routing and resume probing
```

等待队长独立复验，不再追加无关提交。

## 10. 汇报格式

```text
分支与最终提交：
合同条款：
第一阶段 missing_criteria：
Replan 如何映射合同缺口：
暂停前节点快照：
恢复时 current probe：
节点状态变化事件：
最终路由链：
提供给 D/UI 的样例 run_id：
门禁与测试结果：
完整测试结果：
git diff --check：
git status：
已知限制：
是否修改冻结接口：
```
