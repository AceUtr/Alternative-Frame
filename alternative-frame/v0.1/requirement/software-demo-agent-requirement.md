# 软件工程长程 Demo 开发与验收需求书

适用分支：`feature/software-demo`

面向对象：软件 Demo 成员及其 AI Agent

## 1. 最终目标

在 `alternative-frame/v0.1` 中完成一个可由现有 Harness 调度的软件工程长程 Demo。Demo 必须对一个可复现的小型软件项目执行真实分析、修改、测试和证据收集，并且只能在机器可验证的合同全部满足后标记最终目标完成。

最终演示至少包含两个阶段：

1. 第一阶段完成缺陷定位、代码修复和基础测试，但故意保留一个合理且真实可检测的证据缺口，例如缺少回归测试、精确命令证据或变更报告。
2. `GlobalEvaluator` 根据验收合同拒绝完成，Replanner 生成最小恢复 DAG，在第二阶段补齐缺口。
3. 所有必须合同条款通过后，`LongHorizonController` 才允许状态变为 `completed`。

本任务不是编写一段固定的 `code.replace("return a-b", "return a+b")` 脚本，也不是让 Agent 用自然语言声称测试通过。所有代码修改、测试和报告必须来自真实工具调用及本次运行证据。

## 2. 开工前必须阅读

AI Agent 开始修改代码前必须完整阅读：

- `validation/manifests/software.json`
- `docs/team-interface-contract.md`
- `core/models.py`
- `core/domains.py`
- `core/agents.py`
- `core/orchestrator.py`
- `core/acceptance.py`
- `core/tools/`
- `core/local_recovery.py`
- `core/long_horizon/`
- `domains/research_demo.py`，仅参考其 Adapter、合同和长程接入方式，不复制科研逻辑
- `run_research_demo.py`，仅参考控制器组装方式
- `docs/milestone-7-feedback-driven-retry.md`
- `docs/milestone-9-local-dag-recovery-visualization.md`

先向成员汇报现状、风险、拟修改文件和最小方案，再开始编辑。

## 3. 当前已知问题

现有软件 Demo 不能作为基线成果直接宣称完成。AI Agent 必须先确认并逐项消除以下问题：

- `run_software_demo.py` 导入不存在的 `evaluation.evaluator`，入口无法启动。
- `domains/software_demo.py` 没有实现门禁要求的 `SoftwareDomainAdapter`。
- 结构文件 `tests/test_software_demo.py` 和 `docs/software-demo.md` 缺失。
- pytest 失败时 handler 只返回字符串，外层 `DeterministicAgent` 仍可能标记 `success`。
- evaluator 只检查文件存在，不检查代码修改、精确测试命令、退出码和本次运行来源。
- 报告硬编码 `PASS`，没有使用真实测试输出。
- 代码直接使用 `open()`、`str.replace()` 和裸 `subprocess.run()`，未形成标准 `tool_records`。
- 当前入口没有合同、`LongHorizonController`、局部恢复、跨阶段恢复和可恢复状态。

不得只修复导入路径后停止工作。

## 4. 允许修改的范围

成员和其 AI Agent 可以新增或修改：

```text
domains/software_demo.py
domains/software_tools/
examples/software_task/
prompts/software/
tests/test_software_demo.py
run_software_demo.py
docs/software-demo.md
requirement/software-demo-agent-requirement.md
```

如确实需要修改以下队长负责的共享模块，必须先停止并提交接口变更说明，获得队长确认后再改：

```text
core/models.py
core/agents.py
core/orchestrator.py
core/acceptance.py
core/local_recovery.py
core/long_horizon/
core/tools/ 的既有公共接口
ui.py
validation/
```

禁止改变以下冻结接口的字段语义或签名：

```python
SubTask
Plan
AgentResult
AcceptanceContract
Agent.run(task, context)
Tool.execute(arguments)
DomainAdapter
```

## 5. 推荐 Fixture

Demo 应使用普通电脑可在数分钟内完成的小型离线 Python 项目。推荐保留当前加法缺陷作为最小起点，但任务必须扩展到足以证明软件工程闭环，例如：

```text
examples/software_task/
  README.md
  requirements.md
  app.py
  test_app.py
  regression_test.py       # 可在第二阶段补充
  artifacts/               # 运行时生成，不提交陈旧证据
```

Fixture 必须满足：

- 初始状态确定且确实存在可测试缺陷。
- 提供重置方法，每次 Demo 从相同初始状态开始。
- 不访问公网，不依赖 API Key。
- 测试命令精确固定，例如：

```powershell
python -m pytest examples/software_task -q
```

- 不能在开发 Agent 中硬编码最终正确源码。
- 允许提交初始错误 Fixture，不提交带本机时间的运行报告作为完成证据。

## 6. 阶段 S1：接口基线与 Domain Adapter

### 实现要求

在 `domains/software_demo.py` 中实现：

```python
class SoftwareDomainAdapter(DomainAdapter):
    name = "software"

    def register_tools(...): ...
    def build_agents(...): ...
    def build_plan(...): ...
    def build_contract(...): ...
    def reset_workspace(...): ...
```

优先复用现有工具：

- `FileEditor`
- `TestRunner`
- `ShellRunner`
- 必要时增加严格限定在工作区内的软件领域工具

每个 `SubTask` 必须声明：

```text
required_tools
expected_outputs
checks
contract_criteria
depends_on
max_retries
```

### 最小 DAG

建议第一阶段 DAG：

```text
inspect_requirements
        |
inspect_repository
        |
diagnose_failure
        |
implement_fix
        |
run_targeted_tests
        |
build_change_report
```

若任务之间没有依赖，应允许并行；不要为了展示 Agent 数量而制造虚假串行链。

### S1 验收标准

- `SoftwareDomainAdapter` 可导入并通过 Domain preflight。
- Plan 是无环 DAG，所有角色和工具均已注册。
- 所有路径位于 Fixture 工作区。
- `reset_workspace()` 可重复执行且不会删除 Fixture 源文件。
- 不修改冻结接口。

## 7. 阶段 S2：真实工具闭环

### 实现要求

Agent 必须通过工具完成：

1. 读取需求和现有代码。
2. 执行初始测试并保留失败退出码。
3. 定位缺陷。
4. 修改源文件。
5. 执行精确测试命令。
6. 生成变更摘要和证据报告。

标准 `AgentResult` 至少包含：

```text
status
summary
artifacts
evidence
tool_records
failures
attempts
```

测试失败必须返回 `status="failed"`，不得把 `"Tests failed"` 作为成功摘要返回。

报告内容必须读取真实记录，至少包括：

- 修改文件路径；
- 修改前后摘要或 diff；
- 精确测试命令；
- 退出码；
- 测试通过/失败数量；
- 仍存在的风险。

### S2 验收标准

- 初始测试真实失败，修复后真实通过。
- `tool_records` 中有精确命令、参数、退出码和输出摘要。
- 删除修复产物或篡改退出码后，验收必须失败。
- 旧报告文件不能冒充本次运行产物。
- 所有文件和命令均受工作区约束。

## 8. 阶段 S3：结构化验收合同

`build_contract()` 至少声明以下必需条件：

1. 修复后的源文件具有本次运行产物来源。
2. 回归测试文件存在并具有本次运行来源。
3. 精确 pytest 命令返回退出码 0。
4. 变更报告存在并具有本次运行来源。
5. 不能仅凭 Agent 自然语言通过。

建议产物：

```text
artifacts/diagnosis.json
artifacts/change_summary.json
artifacts/test_result.json
artifacts/software_report.md
```

合同中的每个必需 criterion 必须有现有 evaluator 支持。需要新增 `check_type` 时，必须同时提供实现和负向测试，并先获得队长批准。

### S3 验收标准

- 测试未运行时最终合同失败。
- 测试命令不同于合同精确命令时失败。
- 测试退出码非 0 时失败。
- 只有旧文件、没有本次工具来源时失败。
- 所有条件通过后才允许最终完成。

## 9. 阶段 S4：两阶段长程闭环

`run_software_demo.py` 必须使用现有：

```text
LongHorizonController
LongHorizonStore
DeterministicGlobalEvaluator 或 StructuredGlobalEvaluator
LocalDAGRecoveryController
```

第一阶段应真实保留一个合理证据缺口，推荐缺少回归测试或缺少完整变更报告。缺口必须由文件、命令退出码或合同证据真实触发，不得根据 `phase == 1` 直接伪造失败。

第二阶段 Replanner 应根据 `evaluation.missing_criteria` 构建最小恢复 DAG，只补缺失条件，不重复全部任务。

### S4 验收标准

- 第一阶段报告本身可以成功，但全局合同明确拒绝最终完成。
- `missing_criteria` 精确包含预设证据缺口。
- 第二阶段补齐缺口后合同通过。
- `state.json` 显示两阶段，最终状态为 `completed`。
- `events.jsonl` 包含规划、验收、重规划和完成事件。
- 总阶段数、总任务数和重试次数受预算限制。

## 10. 阶段 S5：三层恢复验证

必须提供默认关闭的可控故障注入，仅用于测试和现场演示：

### 第一层：任务重试

- 第一次测试或文件修改注入可恢复失败。
- Agent 收到结构化 `retry_feedback`。
- 第二次尝试改变行动并真实成功。
- `attempts == 2`，且有 `task_retry_scheduled` 事件。

### 第二层：阶段内局部 DAG 恢复

- 一个中间节点在任务重试耗尽后失败。
- 已成功且不受影响的需求分析/仓库检查节点被冻结。
- 只重建失败节点及受影响下游节点。
- 恢复执行计入总任务预算。

### 第三层：跨阶段重规划

- 局部恢复后仍缺少最终合同证据。
- GlobalEvaluator 拒绝完成。
- Replanner 创建后续阶段补齐证据。

### S5 验收标准

- 三层均有独立测试。
- 正式 Demo 支持参数选择故障场景，例如：

```powershell
python run_software_demo.py --fault-scenario none
python run_software_demo.py --fault-scenario retry-once
python run_software_demo.py --fault-scenario local-recovery
```

- 默认运行不注入故障。
- 持续失败不会无限循环，最终停在明确的失败、暂停或预算耗尽状态。

## 11. 阶段 S6：真实模型与 UI 交付

离线确定性 Fixture 通过后，再接入用户配置的 OpenAI-compatible 模型。不得要求用户提交 API Key。

主、子 Agent 可以共享同一个模型，但必须通过角色提示词、上下文和工具权限区分职责。模型不能绕过合同、工作区和命令限制。

UI 最终接入由队长统一完成。成员应提供稳定的 Adapter 和入口，不直接重写 UI。需要向队长提供：

- Adapter 注册方式；
- 可选故障场景；
- DAG 节点及角色；
- 关键指标；
- 产物路径；
- 需要展示的恢复事件。

### S6 验收标准

- Stub/离线模式可重复演示。
- API 模式至少完成一次真实代码修改与测试工具调用。
- UI 能选择软件领域并展示 DAG、合同证据、工具记录和阶段状态。
- API 不可用时不会伪造成功，可暂停或使用明确标记的确定性 fallback。

## 12. 自动化测试最低覆盖

`tests/test_software_demo.py` 至少覆盖：

- Adapter 可导入并通过 preflight。
- Plan 合法、无环、依赖正确。
- 工具拒绝 `..` 和绝对路径越界。
- Fixture 可重置且不会使用上次运行产物。
- 初始测试失败、修复后精确命令退出码为 0。
- 测试失败返回结构化 failed，不会假成功。
- 报告不是硬编码 PASS。
- 缺失文件、陈旧文件和缺少来源时合同失败。
- 第一阶段证据缺口触发第二阶段。
- 任务重试、局部 DAG 恢复和跨阶段恢复受预算限制。
- 运行状态可以持久化并恢复。

## 13. 正式门禁与完成标准

每次申请审核前，在 `alternative-frame/v0.1` 执行：

```powershell
python validate_contribution.py --domain software
python -m pytest tests/test_software_demo.py -q -p no:cacheprovider
python run_software_demo.py
```

阶段性交付还应执行相关共享回归；最终合并前由队长执行完整测试。

只有以下条件全部满足，才可申请最终合并：

- 正式软件贡献门禁为 `passed`。
- 真实 smoke 退出码为 0。
- 没有硬编码 API Key、凭据和个人绝对路径。
- 没有通过固定字符串替换冒充通用修复能力。
- 所有成功结论都有本次运行工具证据。
- 两阶段长程任务真实完成。
- 三层恢复至少在专项测试中可证明，正式入口可以选择演示。
- 文档命令与实际入口一致。
- 不提交 `.pytest_cache`、`__pycache__`、临时审查目录、运行历史和带本机时间的陈旧报告。

## 14. Git 操作规范

成员只能在：

```text
feature/software-demo
```

开发，不得直接向 `main` 推送。

开始工作：

```powershell
git fetch origin
git switch feature/software-demo
git pull --rebase origin feature/software-demo
```

每个提交只完成一个逻辑阶段，推荐提交信息：

```text
fix(software): restore runnable demo entry
feat(software): add domain adapter and workspace tools
feat(software): add contract-backed repair loop
feat(software): add long-horizon recovery flow
test(software): cover failure and recovery scenarios
docs(software): document reproducible demo workflow
```

提交前先检查：

```powershell
git status --short
git diff --check
```

不要提交仓库根目录中的 `.review-research-*` 文件。

## 15. 每阶段向队长汇报的格式

AI Agent 每完成一个阶段必须输出：

```text
当前分支：
Commit：

本次目标：
本次完成：
修改文件：
接口变化：

运行命令及原始结果：
生成产物及路径：
负向测试及结果：

尚未完成：
已知限制：
需要队长确认的事项：
```

不要只报告“已实现”或“测试通过”。必须提供真实 commit hash、命令、退出码、测试数量和产物路径。
