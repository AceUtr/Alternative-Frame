# C 队员：端边云协同运行时开发需求书

## 1. 你的身份与最终目标

你是端边云协同开发 Agent。请协助 C 队员为现有多 Agent Harness 增加“任务放置、节点执行、故障降级、指标记录”的最小运行时。

第一版不要求真实手机、边缘服务器和云服务器。先在一台电脑上模拟 device、edge、cloud 三类节点，但接口必须能在后续替换为真实远程执行器。目标是证明同一份 DAG 可以根据隐私、能力、延迟、成本和网络状态动态选择执行位置。

## 2. 开工前必须阅读

请先完整阅读：

- `core/models.py`
- `core/orchestrator.py`
- `core/tool_calling_agent.py`
- `core/tools/`
- `core/metrics.py`
- `core/long_horizon/state.py`
- `core/long_horizon/controller.py`
- `docs/architecture-baseline.md`
- `docs/milestone-9-local-dag-recovery-visualization.md`

先输出一份不超过一页的适配说明，指出执行节点应接在“任务调度”和“Tool 实际执行”之间的哪个位置。未经队长确认，不要大改 Orchestrator。

## 3. 任务边界

你可以新增或修改：

```text
core/runtime_nodes/
core/routing/
examples/edge_cloud/
tests/test_node_routing.py
tests/test_runtime_fallback.py
docs/edge-cloud.md
run_edge_cloud_demo.py
```

不得自行改变以下公共数据结构的已有字段语义：

```python
SubTask
Plan
AgentResult
AcceptanceContract
Agent.run()
Tool.execute()
```

需要给 `SubTask.metadata` 或 `AgentResult.tool_records` 增加端边云信息时，使用兼容的附加字段，不删除现有字段。不得把真实 API Key、主机密码或 Token 落盘。

## 4. 必须提供的抽象

至少实现以下概念，名称可以细调，但职责不可缺少：

```python
ExecutionNode       # 节点统一接口
DeviceNode          # 隐私优先、资源有限
EdgeNode            # 中等能力、低网络时延
CloudNode           # 能力强、成本较高、依赖网络
TaskRequirements    # 任务对隐私、资源、时延、工具的要求
PlacementDecision   # 选择结果和可解释原因
NodeRouter           # 节点筛选、评分和选择
RuntimeExecutor      # 在选定节点执行，并记录结果
```

`ExecutionNode` 至少应暴露：节点 ID、节点类型、在线状态、能力/工具集合、资源容量、估算延迟、估算成本和执行方法。

## 5. 路由规则

每个任务至少考虑以下约束：

- `privacy_level`：敏感任务是否禁止离开 device。
- `required_capabilities`：节点是否具有需要的工具或算力。
- `max_latency_ms`：预计时延是否可接受。
- `max_cost`：预计成本是否超限。
- `network_required` / 节点在线状态。
- `preferred_tier`：仅为偏好，不能覆盖硬约束。

先应用硬约束过滤，再对候选节点评分。`PlacementDecision` 必须记录被选节点、得分、选择原因和被拒节点的原因，不能只返回字符串 `cloud`。

默认降级顺序不是永远固定的。建议按任务要求产生候选顺序，并至少演示：

```text
普通高算力任务：cloud → edge → device
隐私敏感任务：device（不可偷偷上传）
低时延且 edge 可用：edge → device
```

## 6. 实现步骤

### 阶段 C1：纯路由器

- 使用 dataclass 或清晰的类型实现节点、需求和决策。
- 路由算法保持确定性，相同输入得到相同结果。
- 写单元测试覆盖隐私、能力不足、离线、成本和延迟。
- 此阶段不接 Orchestrator，不执行真实工具。

### 阶段 C2：单机模拟执行

- 三类节点都在本机执行，但使用独立节点 ID 和能力配置。
- RuntimeExecutor 将节点信息写入 `tool_records`，至少包括：

```json
{
  "node_id": "edge-1",
  "node_type": "edge",
  "placement_reason": "...",
  "estimated_latency_ms": 20,
  "actual_duration_ms": 31,
  "fallback_count": 0
}
```

- 节点执行失败时只对允许迁移的任务尝试下一个候选节点。
- 隐私硬约束、工作区限制和工具权限在降级过程中仍必须成立。

### 阶段 C3：故障与降级 Demo

`run_edge_cloud_demo.py` 至少展示三个任务：

1. 敏感文件处理固定在 device。
2. 低时延任务优先 edge。
3. 高算力任务原选 cloud，模拟 cloud 离线后自动降级并成功。

日志必须能看出路由原因、失败节点、降级节点和最终结果。不要用随机失败；使用可控制的故障注入，保证演示可重复。

### 阶段 C4：最小 Harness 接入

- 提供一个小而清晰的适配器，由队长接入主 Orchestrator。
- 不要复制 LongHorizonController 或创建第二套任务状态机。
- 本地恢复和跨阶段恢复仍由现有 Harness 管理；节点降级只处理一次任务执行中的放置失败。

### 阶段 C5：后续真实节点扩展点

在文档中说明未来如何增加 HTTP/gRPC/SSH/设备执行器，但本次不要求实现不安全的远程命令功能。节点认证、传输加密和隐私策略必须列入风险，不得把模拟器描述成已完成真实端边云部署。

## 7. 完成标准

- 五类路由因素都有测试：隐私、能力、延迟、成本、网络状态。
- 路由决策可解释且可持久化。
- cloud 故障能触发合规降级，最终证据保留完整执行链。
- 隐私任务在任何故障下都不会迁移到 edge/cloud。
- 单机 Demo 可重复运行，不需要公网或 API Key。
- 代码与现有 Harness 类型兼容。

建议验收命令：

```powershell
cd "E:\Users\wang\Documents\plan a project\alternative-frame\v0.1"
python -m pytest tests/test_node_routing.py tests/test_runtime_fallback.py -q
python run_edge_cloud_demo.py
```

## 8. 每次让 AI Agent 工作时的汇报格式

```text
本次完成：
路由/降级规则：
修改文件：
测试命令及结果：
演示输出摘要：
未完成和风险：
需要队长确认的核心改动：
```

禁止只给架构图而没有可运行代码，也禁止为了接入而大范围重构主 Harness。
