# 团队接口契约与合并规则

版本：v0.1

本文是 B、C、D 队员及其 AI Agent 的共同开发边界。任何实现若违反本文，先修改实现或提交接口变更说明，不直接合并到主线。

## 1. 当前主线职责

队长负责：

- `core/orchestrator.py`
- `core/local_recovery.py`
- `core/long_horizon/`
- `core/models.py`
- `core/main_agent.py`
- 主 `ui.py` 的最终接线
- 跨分支集成、真实 API 演示和比赛材料最终确认

B 队员负责科研 Demo，C 队员负责端边云运行时，D 队员负责评测和交付。各自的详细要求见 `requirement/` 目录。

## 2. 冻结的数据接口

### `SubTask`

```python
@dataclass
class SubTask:
    id: str
    role: str
    description: str
    depends_on: list[str]
    inputs: list[str]
    acceptance: list[str]
    max_retries: int = 2
    metadata: dict[str, Any] = field(default_factory=dict)
```

领域扩展必须放在 `metadata` 中，例如 `required_tools`、`expected_outputs`、`checks`、`privacy_level`、`placement_requirements`。不得新增同义顶层字段，也不得删除已有字段。

### `Plan`

```python
@dataclass
class Plan:
    goal: str
    subtasks: list[SubTask]
    final_acceptance: list[str] = field(default_factory=list)
```

计划必须是有向无环图。所有依赖必须指向存在的任务 ID。领域模块不得另建一套平行计划对象。

### `AgentResult`

```python
@dataclass
class AgentResult:
    subtask_id: str
    status: str                  # success / failed / timeout
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    tool_records: list[dict[str, Any]] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    attempts: int = 1
```

工具、节点、实验和模型信息必须追加到 `tool_records` 或 `evidence`，不能只写日志文本。领域代码不能把 `failed` 改成 `success` 来绕过验收。

### `AcceptanceContract`

合同由 `GoalCriterion` 构成。每个必需条款必须能映射到具体文件、命令、指标或人工确认项。新的 `check_type` 必须同时提供验证实现和测试；没有验证器的字符串不能作为完成条件。

### Agent 与 Tool

```python
Agent.run(task: SubTask, context: Mapping[str, AgentResult]) -> AgentResult
Tool.execute(arguments: dict[str, Any]) -> ToolResult
```

Agent 负责决策和调用工具，Tool 负责可验证的实际动作。Tool 必须返回结构化状态、摘要、产物、证据和错误信息。不得让 Tool 直接修改全局 LongHorizon 状态机。

## 3. 证据和产物要求

每个成功任务至少应满足以下一项，并尽量满足多项：

- 明确产物的相对路径，并确认文件存在。
- 精确执行命令、退出码和关键输出。
- 可解析的指标名称、数值和阈值。
- 真实工具调用记录和开始/结束时间。

所有路径必须位于当前任务工作区或项目允许的产物目录内。禁止使用绝对个人路径作为合同唯一依据。旧文件不能自动冒充本次运行产物，验证时要保留本次运行来源信息。

## 4. AI Agent 开发协议

每位队员给 AI Agent 的首条指令必须要求：

1. 先阅读本契约和自己目录下的需求书。
2. 先检查现有实现和测试，不重复造轮子。
3. 先提交最小设计和拟修改文件列表。
4. 分阶段实现，每阶段运行测试。
5. 不修改职责范围外的核心文件；如必须修改，先停下并报告原因。

每次工作结束必须报告：

```text
目标：
修改文件：
接口变化：
运行命令与结果：
新增产物/证据：
未完成事项：
风险与需要队长决策的内容：
```

## 5. Git 协作规则

建议分支：

```text
main
feature/research-demo
feature/edge-cloud-runtime
feature/evaluation-dashboard
```

队员不得直接向 `main` 推送。一个提交只完成一个逻辑阶段，提交信息采用：

```text
feat(research): add reproducible experiment fixture
feat(runtime): add deterministic node routing
feat(eval): add benchmark metrics schema
test(...): add regression coverage
docs(...): document demo and reproducibility
```

提交前必须运行与本模块相关的测试，并在 Pull Request 中列出命令、结果和已知限制。队长负责解决跨模块冲突和最终合并。

## 6. 合并门禁

任何分支合并前必须通过：

- 相关单元测试和导入检查。
- 至少一个真实可运行的 smoke Demo。
- 不改变已有 LongHorizon、合同确认、局部恢复测试的行为。
- 不新增硬编码 API Key、凭据、个人机器路径或不可复现的随机结果。
- 文档中的命令与实际入口一致。
- 产物、证据和指标可以从 `run_id` 追溯。

队长集成后再运行完整回归测试和双领域演示；单个队员不应自行宣称“比赛完成”。

## 7. 变更接口的流程

如果需求确实需要改变冻结接口，提交一份变更说明，至少包含：

- 旧接口和新接口的完整签名。
- 为什么无法使用 `metadata` 或适配器解决。
- 受影响模块和迁移步骤。
- 向后兼容方案。
- 新增测试和回滚方法。

未获得队长确认前，AI Agent 只能在自己的模块内提供适配器或草稿实现。
