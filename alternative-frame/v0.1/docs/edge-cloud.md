# 端边云协同运行时 v0.1

## 目标

本模块在单机上模拟 `device`、`edge`、`cloud` 三类节点，为同一份任务提供可解释的放置决策、执行记录和故障降级。它不宣称已经完成真实手机或远程云节点部署。

## 接入位置

```text
SubTask.metadata
  -> TaskRequirements
  -> NodeRouter
  -> PlacementDecision
  -> RuntimeExecutor
  -> AgentResult.tool_records
```

节点路由位于任务调度和实际工具执行之间。核心 `Orchestrator`、`LongHorizonController`、`SubTask`、`Plan` 和 `AgentResult` 的字段语义保持不变。

`NodeRoutedAgent` 是最小 Harness 适配器。它包装已有角色 Agent，使用任务的 `metadata` 构造路由要求，并把运行记录追加到 Agent 原有的 `tool_records`。因此普通 `Orchestrator` 和长程控制器不需要增加端边云专用分支。

```python
registry.register(
    NodeRoutedAgent(
        existing_agent,
        [device_node, edge_node, cloud_node],
    )
)
```

## 硬约束

- 离线节点不可选择。
- `network_required=True` 时，节点必须有网络。
- `sensitive` 数据只能留在 `device`。
- 节点必须满足全部 `required_capabilities`。
- 预计延迟和成本不得超过任务上限。

硬约束通过后，再根据偏好层级、延迟和成本进行确定性评分。相同输入始终产生相同排序。

## 故障降级

`RuntimeExecutor` 只会在已经通过硬约束的候选节点之间降级。因此隐私任务即使执行失败，也不会迁移到 edge 或 cloud。每次失败和后续成功都会形成独立 `tool_records` 记录。

只有 `NodeExecutionError` 会触发跨节点降级。Agent 业务异常不会在另一节点重复执行，而是交回现有 Orchestrator 的任务级重试机制，避免非幂等操作被重复执行。

## 验证

```powershell
python -m unittest -v tests.test_node_routing tests.test_runtime_fallback
python run_edge_cloud_demo.py
```

## 后续真实节点扩展

未来可为 `ExecutionNode.execute()` 增加 HTTP、gRPC 或受控设备执行适配器，但需要额外解决双向认证、传输加密、命令白名单、超时、幂等性、日志脱敏和产物传输。当前版本不提供 SSH 或任意远程命令执行。
