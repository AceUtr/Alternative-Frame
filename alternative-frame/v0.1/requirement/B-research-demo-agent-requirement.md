# B 队员：科研长程 Demo 开发需求书

## 1. 你的身份与最终目标

你是本项目的科研 Demo 开发 Agent。请协助 B 队员把现有 `autoresearch-master` 的科研能力接入 `alternative-frame/v0.1`，形成一个可被主 Harness 调度、可真实执行、可采集证据、可由验收合同判定完成的科研长程 Demo。

这不是再写一套独立多 Agent 框架，也不是让模型只输出一篇“研究报告”。最终 Demo 必须执行真实工具、产生真实文件和指标，并能展示至少两个阶段：先完成实验，再根据证据缺口补充验证或改进。

## 2. 开工前必须阅读

请先完整阅读以下文件，再修改代码：

- `core/models.py`
- `core/orchestrator.py`
- `core/tool_calling_agent.py`
- `core/tools/`
- `core/long_horizon/acceptance_contract.py`
- `core/long_horizon/evidence.py`
- `domains/presets.py`
- `run_real_two_phase_demo.py`
- `docs/milestone-7-feedback-driven-retry.md`
- `docs/milestone-9-local-dag-recovery-visualization.md`
- 仓库根目录下 `autoresearch-master` 的 README、入口程序和实验执行代码

先向 B 队员汇报你识别到的可复用能力、依赖、输入、输出和风险，再开始编辑。

## 3. 任务边界

你可以新增或修改：

```text
domains/research_demo.py
domains/research_tools/
examples/research_task/
prompts/research/
tests/test_research_demo.py
run_research_demo.py
docs/research-demo.md
```

如确实需要修改核心接口，先说明原因并等待队长确认。不得自行重写以下接口或改变字段语义：

```python
SubTask
Plan
AgentResult
AcceptanceContract
Agent.run()
Tool.execute()
```

不得把 API Key 写入代码、配置文件、测试、日志或提交记录。不得直接改 UI；UI 接入由队长统一完成。

## 4. 推荐的最小科研任务

选择一个可在普通电脑上数分钟内完成、结果可重复的轻量实验。例如：在固定小数据集上比较两个文本分类或回归方案，输出最优配置、指标、图表和研究报告。

任务至少包含：

1. 数据准备和数据检查。
2. 基线实验。
3. 至少一个改进实验或参数搜索。
4. 使用独立命令复验最优结果。
5. 生成结构化指标 JSON、图表和 Markdown 报告。

不得依赖人工预先放置“正确答案”；不得用 stub、固定字符串或模型口头声明冒充实验成功。

## 5. 实现步骤

### 阶段 B1：审计与适配设计

- 找出 `autoresearch-master` 中真正执行实验、读取指标、比较结果和保存产物的代码。
- 将其能力包装成 Tool，而不是调用它自己的总控循环。
- 为每个 Tool 定义结构化输入、输出、错误信息、超时和工作区限制。
- 写出 `docs/research-demo.md` 的架构和数据流。

建议至少提供：

```text
DatasetInspector
ExperimentRunner 或 AutoresearchExperimentTool
MetricComparator
ResearchReportBuilder
```

优先复用现有 `core/tools/experiment_runner.py`；只有现有能力不足时才新增工具。

### 阶段 B2：建立真实科研 Fixture

- 在 `examples/research_task/` 放入小型、合法、可提交的数据或生成脚本。
- 固定随机种子和依赖版本。
- 提供清理/重置方法，确保每次 Demo 从相同初始状态开始。
- 所有产物必须写入该任务工作区内的明确目录。

推荐产物：

```text
artifacts/baseline_metrics.json
artifacts/improved_metrics.json
artifacts/best_config.json
artifacts/comparison.png
artifacts/research_report.md
```

### 阶段 B3：合同与 DAG

在 `domains/research_demo.py` 中定义科研任务的角色、工具权限和计划生成入口。每个子任务必须声明：

- `required_tools`
- `expected_outputs`
- 结构化 `checks`
- 对应的 `contract_criteria`
- 清晰的依赖关系

初始 DAG 应允许数据检查后并行运行可独立的实验，最终比较和报告任务依赖实验结果。

### 阶段 B4：长程闭环

- `run_research_demo.py` 必须使用现有 `LongHorizonController`。
- 第一阶段故意保留一个合理的证据缺口，例如缺少独立复验或比较图。
- `GlobalEvaluator` 应拒绝完成。
- Replanner 新增后续阶段补齐缺口。
- 最终所有必需合同条款通过后，状态才允许变为 `completed`。

不要在代码里根据阶段编号直接伪造结果；缺口必须由文件、命令退出码或指标检查真实触发。

### 阶段 B5：测试和文档

至少覆盖：

- 科研计划是合法无环 DAG。
- 工具只能在工作区内读写。
- 实验命令退出码和指标被记录进 `tool_records`。
- 缺失指标/文件时验收失败。
- 复验成功后验收通过。
- 固定种子下关键指标可重复。

## 6. 完成标准

以下条件必须全部满足，才可以向队长申请合并：

- Demo 使用真实本地工具执行，不是 DeterministicAgent 自述完成。
- 至少产生一个机器可读指标文件、一张图和一份研究报告。
- 验收证据包含产物路径、精确命令、退出码和解析后的指标。
- 可演示一次“第一阶段不完整，后续阶段自动补齐”的长程过程。
- 从全新环境按文档命令可复现。
- 测试不会访问公网，不需要真实 API Key。

建议验收命令：

```powershell
cd "E:\Users\wang\Documents\plan a project\alternative-frame\v0.1"
python -m pytest tests/test_research_demo.py -q
python run_research_demo.py
```

## 7. 每次让 AI Agent 工作时的汇报格式

完成一个阶段后，必须输出：

```text
本次完成：
修改文件：
运行命令及结果：
生成产物：
尚未完成：
风险或需要队长确认：
```

不要只说“已实现”。必须给出真实命令结果和产物位置。
