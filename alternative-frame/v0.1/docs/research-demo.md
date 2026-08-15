# 科研长程 Demo：审计与适配设计

状态：B2 两阶段科研闭环已实现，待队长审核
分支：`feature/research-demo`

## 1. 目标与边界

本 Demo 将 `autoresearch-master` 中可复用的科研执行与评测模式接入
`alternative-frame/v0.1`，使科研任务能够：

1. 被现有 Harness 以 `Plan` / `SubTask` 调度；
2. 通过真实本地工具执行实验；
3. 记录命令、退出码、耗时、指标和产物路径；
4. 由 `AcceptanceContract` 和证据门禁判定是否完成；
5. 在第一阶段证据不足时，由后续阶段补充复验或产物。

本模块不会创建第二套 Agent、计划或长程控制框架，也不会修改以下冻结接口：

```text
SubTask
Plan
AgentResult
AcceptanceContract
Agent.run()
Tool.execute()
```

领域扩展信息统一放入 `SubTask.metadata`。本模块不修改主 UI，不保存 API Key，
测试不访问公网。

## 2. `autoresearch-master` 能力审计

审计源是独立提供的 `autoresearch-master` 仓库。接入实现不会依赖该仓库在
开发者电脑上的绝对路径，也不会将个人路径写入运行合同、测试或最终产物。

### 2.1 原始训练路径

| 文件 | 能力 | 输入 | 输出 | 复用结论 |
| --- | --- | --- | --- | --- |
| `prepare.py` | 下载数据、训练 tokenizer、提供 dataloader 与 BPB 评估 | 数据分片数量、缓存目录 | Parquet 数据、tokenizer 缓存 | 设计可参考；默认联网且写入用户缓存，不直接用于离线 Demo |
| `train.py` | 执行固定时间预算的 GPT 训练和最终评估 | 模型/优化器参数、已准备数据 | 标准输出中的 `val_bpb`、显存、耗时等指标 | 指标输出协议可复用；训练依赖 NVIDIA GPU，不作为默认 Fixture |
| `program.md` | 规定 baseline、候选实验、比较和保留/丢弃循环 | 研究目标与代码状态 | 实验日志和 `results.tsv` | 科研工作流可复用；不调用其自主总控循环 |

原始训练的核心比较指标为 `val_bpb`，越低越好。单次训练预算约五分钟，
依赖 PyTorch CUDA、NVIDIA GPU，并需要联网准备数据，因此不能作为普通电脑、
离线测试的默认验收路径。

### 2.2 Prompt 评测路径

| 文件 | 能力 | 输入 | 输出 | 复用结论 |
| --- | --- | --- | --- | --- |
| `agent.py` | 调用 OpenAI-compatible Chat Completions | Prompt、任务、环境变量配置 | 文本响应、模型信息、耗时 | Provider-neutral 调用方式可参考；默认需要网络和 API Key |
| `evaluator.py` | 校验固定任务集、确定性评分、聚合指标 | `tasks/eval.json`、Agent 输出 | overall score、成功率、错误率、逐题结果 | 数据校验、确定性评分和结构化汇总模式可复用 |
| `run_eval.py` | 提供检查与完整评测入口 | `--check` 或完整运行 | 退出码、标准输出、`summary.json` | 命令入口和结构化运行结果模式可复用 |

`run_eval.py --check` 可离线检查配置，但完整评测需要真实模型 API。自动测试和
默认 Demo 不应依赖这条联网路径。

### 2.3 可复用的通用科研模式

不直接复制 `autoresearch-master` 的 Agent 循环，复用以下领域能力：

- 固定、可审计的任务或数据定义；
- baseline 先行；
- 至少一个候选实验；
- 统一预算与确定性评分；
- 从真实运行输出解析指标；
- 比较候选结果并选择最佳配置；
- 使用独立命令复验最佳结果；
- 按运行保存结构化指标和研究记录；
- 失败实验保留失败结论，不伪装成成功。

## 3. 当前 Harness 可直接复用的能力

| 现有组件 | 复用方式 |
| --- | --- |
| `core.tools.Tool` / `ToolResult` | 所有科研工具遵循统一执行接口和结构化结果 |
| `ShellRunner` | 在任务工作区执行命令，记录退出码、输出和耗时 |
| `ExperimentRunner` | 作为实验命令执行的基础适配器，解析标准输出中的数值指标 |
| `ToolRegistry` | 注册科研角色允许调用的工具 |
| `ToolCallingAgent` | 将工具调用写入 `tool_records`，收集产物和指标元数据 |
| `Plan.validate()` | 验证任务 ID、依赖关系和 DAG 无环性 |
| `Orchestrator` | 在依赖满足后并行执行独立实验 |
| `HardEvidenceGate` | 验证本次运行的文件、精确命令、退出码和指标阈值 |
| `LongHorizonController` | 在全局验收失败后进入下一阶段 |

现有 `ExperimentRunner` 适合执行会在标准输出中打印 `name=value` 或
`name: value` 的实验。科研适配器还需要补充 JSON 指标读取、产物登记和更明确
的参数约束，但无需修改核心 `ExperimentRunner`。

## 4. 最小科研任务的选择条件

队长已批准轻量离线适配方案。第一阶段 Fixture 采用固定种子生成的二维二分类
数据和最近类中心 baseline；后续实验仍须满足：

- 普通电脑数分钟内完成；
- 无 GPU 强制依赖；
- 测试不访问公网、不需要 API Key；
- 数据合法、固定且可提交，或由确定性脚本生成；
- 固定随机种子和依赖版本；
- baseline 与候选方案使用同一数据划分和评分规则；
- 指标来自真实运行，不使用硬编码“正确答案”；
- 最佳配置可用独立命令复验；
- 能生成 JSON 指标、比较图和 Markdown 报告。

当前固定配置：

- 数据版本：`synthetic-centroids-v2`；
- Python 随机种子：`1729`；
- 固定划分：160 条训练数据、40 条测试数据；
- baseline：仅使用基础特征 `x1`、从训练集拟合的最近类中心分类器；
- 主指标：测试集 `accuracy`，越高越好；
- 依赖：Python 3.10+ 标准库，不访问公网，不读取 API Key。

第一阶段接口审查通过后，第二阶段已在同一 Fixture 上增加双特征 improved 实验、
指标比较、独立复验、PNG 图表、Markdown 报告和两阶段跨阶段证据补齐。
固定种子下当前 baseline accuracy 为 `0.80`，处于预定的 `0.75～0.90`
区间。数据同时保留第二个有效特征，但第一阶段 baseline 不使用它，为后续真实改进
保留空间；任何后续提升仍必须由独立实验命令产生，不能改写或写死指标。

## 5. Adapter 设计

所有工具只接受相对当前任务工作区的路径。解析后的路径必须仍位于工作区内；
绝对路径和 `..` 越界路径应返回失败。工具不得修改全局 LongHorizon 状态。

### 5.1 `DatasetInspector`

职责：检查数据是否存在、结构是否合法，并生成机器可读的数据摘要。

结构化输入：

```json
{
  "dataset_path": "data/dataset.json",
  "output_path": "artifacts/dataset_summary.json",
  "required_fields": ["text", "label"]
}
```

结构化输出元数据：

```json
{
  "artifacts": ["artifacts/dataset_summary.json"],
  "dataset": {
    "rows": 0,
    "columns": [],
    "label_distribution": {}
  }
}
```

失败条件包括：路径越界、文件不存在、格式无法解析、必需字段缺失、数据为空。

### 5.2 `ExperimentRunner` / `AutoresearchExperimentTool`

职责：使用允许的实验入口运行 baseline、候选方案或独立复验。

结构化输入：

```json
{
  "command": "python experiment.py --config configs/baseline.json",
  "metrics_path": "artifacts/baseline_metrics.json",
  "expected_artifacts": ["artifacts/baseline_metrics.json"],
  "timeout_seconds": 120
}
```

结构化输出元数据：

```json
{
  "command": "精确执行命令",
  "metrics": {},
  "artifacts": [],
  "experiment_kind": "baseline"
}
```

工具必须保留成功或失败状态、退出码、耗时、标准输出摘要和解析后的指标。非零退出
码、超时、缺少指标文件或指标 JSON 非法均视为失败。

### 5.3 `MetricComparator`

职责：读取多个真实实验指标，按照声明的方向选择最佳方案并输出最佳配置。

结构化输入：

```json
{
  "metric_files": [
    "artifacts/baseline_metrics.json",
    "artifacts/improved_metrics.json"
  ],
  "primary_metric": "accuracy",
  "mode": "max",
  "output_path": "artifacts/best_config.json"
}
```

结构化输出元数据：

```json
{
  "metrics": {"best_score": 0.0},
  "artifacts": ["artifacts/best_config.json"],
  "best_experiment": "baseline-or-candidate"
}
```

失败条件包括：输入文件缺失、指标不一致、主指标缺失、数值非法或比较模式无效。

### 5.4 `ResearchReportBuilder`

职责：根据数据摘要、实验指标、最佳配置和复验结果生成比较图与 Markdown 报告。

结构化输入：

```json
{
  "metrics_files": [],
  "best_config_path": "artifacts/best_config.json",
  "verification_metrics_path": "artifacts/verification_metrics.json",
  "chart_path": "artifacts/comparison.png",
  "report_path": "artifacts/research_report.md"
}
```

结构化输出元数据：

```json
{
  "artifacts": [
    "artifacts/comparison.png",
    "artifacts/research_report.md"
  ]
}
```

报告必须引用真实指标，并明确写出候选方案相对 baseline 是提升、持平还是失败。
失败实验不能被报告为成功。

## 6. 数据流与初始 DAG

```text
inspect_dataset
       |
       +------------------+
       |                  |
run_baseline       run_candidate
       |                  |
       +--------+---------+
                |
        compare_experiments
                |
        build_initial_report
```

数据检查完成后，互相独立的 baseline 与候选实验可以并行运行。比较任务依赖两个
实验结果，初始报告依赖比较结果。

每个 `SubTask.metadata` 至少包含：

```python
{
    "required_tools": [],
    "expected_outputs": [],
    "checks": [],
    "contract_criteria": [],
}
```

所有依赖只引用同一 `Plan` 中存在的任务 ID，计划必须通过 `Plan.validate()`。

## 7. 已实现的两阶段长程闭环

第一阶段执行数据检查、baseline、候选实验、比较和初始报告，并保留一个可被硬证据
门禁发现的真实缺口：没有 `verification_metrics.json` 和复验命令记录。Replanner
根据全局验收返回的缺失条款生成复验计划，不根据阶段编号伪造失败。

```text
第一阶段真实实验
  -> 缺少 verification_metrics.json 或精确复验命令证据
  -> GlobalEvaluator 拒绝完成
  -> Replanner 生成复验/补充报告任务
  -> 独立命令复验最佳配置
  -> 更新报告并补齐证据
  -> 所有合同条款通过
  -> completed
```

缺口必须由文件不存在、精确命令没有退出码 0 记录，或指标检查不通过真实触发。
独立复验会真实重跑 `best_config.json` 指定的配置，并要求实际 `accuracy` 与
`best_score` 的绝对差不超过 `1e-9`。不一致时复验文件会记录差值和失败状态，
命令返回非零退出码，因此精确命令证据与全局合同均不能通过。

第三阶段增加了机器可验收的 `improvement_delta` 合同条款：

```text
improvement_delta = improved_accuracy - baseline_accuracy
improvement_delta >= 0.000001
```

因此 baseline 和 improved 即使分别达到绝对 accuracy 门槛，只要 improved
持平或退化，任务验收与全局合同仍会拒绝完成。

科研 Adapter 还提供默认关闭、只能由任务元数据显式开启的确定性故障注入。
测试分别验证：

- `run_baseline` 设置 `max_retries=1`，第一次注入瞬时失败，第二次真实工具执行成功；
- `run_improved` 设置 `max_retries=0`，首次失败后由现有
  `LocalDAGRecoveryController` 重建受影响子图；
- 局部恢复只重跑 `run_improved -> compare_experiments -> build_initial_report`；
- `generate_dataset`、`inspect_dataset` 和 `run_baseline` 保持冻结，不重复执行。

上述结论仅覆盖受控、确定性的单次故障。baseline、improved 和独立复验任务采用
有限的 `max_retries=1`，其他科研任务仍为 `max_retries=0`，正常运行不启用
故障注入；尚未证明任意外部故障均可恢复。
跨阶段复验缺口目前仍由确定性规则选择恢复计划，动态科研 Replanner
和真实模型协作仍属于后续工作。

### 7.1 正式入口中的恢复场景

`run_research_demo.py` 已正式接入现有 `LocalDAGRecoveryController`，不创建第二套
恢复控制器。命令行通过 `--fault-scenario` 选择三个确定性场景：

```powershell
python run_research_demo.py --fault-scenario normal
python run_research_demo.py --fault-scenario task-retry
python run_research_demo.py --fault-scenario local-recovery
```

- `normal`：不注入故障，局部恢复周期为 0；
- `task-retry`：baseline 首次真实命令写入错误产物路径，验收产生
  `missing_artifact` 类型的 `retry_feedback`；Agent 随后清理错误产物、
  将命令参数修回合同路径并重新执行；
- `local-recovery`：improved 首次注入瞬时失败且该任务本轮
  `max_retries=0`，由局部恢复控制器冻结稳定节点并重建受影响子图。

任务开始、结束、重试安排、局部恢复计划和恢复结果均写入对应 run 目录的
`events.jsonl`。状态与阶段级 `local_recovery_cycles`、`executed_task_count`
写入 `state.json`，可供后续 UI 展示和现场审计。

### 7.2 三层恢复的准确边界

Demo 复用现有 Harness 的三层机制：

1. 任务级反馈重试：`task-retry` 根据 `retry_feedback` 修正命令并清理错误产物；
2. 阶段内局部 DAG 恢复：`local-recovery` 冻结稳定节点，只重建受影响子图；
3. 跨阶段全局补证：第一阶段缺少独立复验时，GlobalEvaluator 拒绝完成，第二阶段
   生成最小复验 DAG。

上述能力仅验证受控、确定性的演示故障，不代表能够恢复任意外部服务、硬件或系统故障。

### 7.3 UI 操作

启动主界面：

```powershell
python ui.py
```

选择 `Research Demo (offline)` 和一个故障场景。固定科研目标会自动填入，运行模式
自动切换到本地 Stub，不需要 API Key。点击开始后先预览验收合同；取消时不会创建
Controller，也不会执行工具。确认后可在任务表、DAG、日志和验收证据页查看阶段、
节点、attempts、工具参数、退出码、产物、`global_hard_gate`、重试与恢复事件。
暂停按钮复用 `active_controller`，在安全阶段边界暂停。最终日志显示研究报告和
`state.json` 路径。

## 8. 产物与证据规范

建议的任务工作区产物：

```text
artifacts/dataset_summary.json
artifacts/baseline_metrics.json
artifacts/improved_metrics.json
artifacts/best_config.json
artifacts/verification_metrics.json
artifacts/comparison.png
artifacts/research_report.md
```

成功任务至少记录：

- 相对工作区的产物路径；
- 本次运行的产物来源；
- 精确命令和退出码；
- 开始/结束时间或耗时；
- 解析后的指标名称和值；
- 失败时的结构化错误信息。

旧产物不能直接通过本次验收。所有运行结果应能通过 `run_id` 追溯。

## 9. 测试策略

`tests/test_research_demo.py` 至少覆盖：

1. 科研计划是合法无环 DAG；
2. 每个任务声明必需的 metadata；
3. 工具拒绝工作区外路径；
4. 实验命令退出码和指标进入 `tool_records`；
5. 缺少指标文件时任务或全局验收失败；
6. 缺少独立复验时第一阶段不能完成；
7. 复验成功后合同通过；
8. 固定随机种子下关键指标可重复；
9. 测试不访问公网且不要求 API Key。

计划验收命令：

```powershell
python -m pytest tests/test_research_demo.py -q
python run_research_demo.py
```

## 10. 拟修改文件

按阶段新增或修改：

```text
domains/research_demo.py
domains/research_tools/__init__.py
domains/research_tools/dataset_inspector.py
domains/research_tools/metric_comparator.py
domains/research_tools/research_report_builder.py
examples/research_task/
prompts/research/
tests/test_research_demo.py
run_research_demo.py
docs/research-demo.md
```

第一阶段实际新增：

```text
domains/research_demo.py
domains/research_tools/__init__.py
domains/research_tools/dataset_inspector.py
examples/research_task/README.md
examples/research_task/generate_dataset.py
examples/research_task/run_baseline.py
tests/test_research_demo.py
prompts/research/research_prompt.md
run_research_demo.py
```

当前设计和实现未修改 `core/` 冻结接口。主 `ui.py` 仅注册离线 Research 模式并
复用现有合同确认、DAG、事件、证据和暂停组件，没有新增第二套 UI 状态机。
`ResearchDomainAdapter.reset_workspace()` 只删除声明过的生成文件，并保留 Fixture
源码和其他未知文件；重复调用得到相同的干净初始状态。
`run_research_demo.py` 使用现有 `LongHorizonController` 运行两阶段真实科研闭环，
没有创建第二套状态机或长程循环。

## 11. 已知风险与待确认事项

已知限制：

- 原始 `autoresearch` 训练依赖 NVIDIA GPU，数据准备需要公网；
- Prompt 评测路径的完整运行依赖模型 API 和 API Key；
- 现有 `ExperimentRunner` 只从标准输出提取简单数值，需要领域 Adapter 补充
  JSON 指标和产物登记；
- `ShellRunner` 可以设置工作目录和超时，但科研 Adapter 仍需对所有输入/输出
  路径做显式工作区校验。
- 默认 CLI 使用共享 Fixture 工作区，但每次运行前只删除白名单内生成产物；
  遇到 Windows 文件锁会明确失败，不会把旧产物继续作为新运行证据；
- 当前未实现动态模型科研 Replanner，也不执行原始 GPU 训练或联网 Prompt 评测。

已由队长确认：

1. 使用普通电脑可运行的轻量离线实验作为默认 Fixture；
2. 接受“复用科研模式和确定性评测设计”，不默认执行 H100 训练；
3. 第一阶段使用固定生成数据、最近类中心 baseline 和 accuracy。

第二阶段已采用双特征最近类中心方案作为可解释的 improved experiment；后续若扩展
算法搜索空间，仍需保持同一数据、划分、种子和评分规则。

## 12. `autoresearch-master` 复用清单

以下边界基于 `D:\AI_Agent\autoresearch-master` 的 README、`program.md`、
`prepare.py`、`train.py`、`agent.py`、`evaluator.py` 和 `run_eval.py` 审计。
该绝对路径仅记录审计来源，不会进入运行时、合同或测试。

### 12.1 代码级复用

第一阶段没有复制或导入 `autoresearch-master` 的 Python 实现。原因如下：

- `prepare.py` 会从公网下载 Parquet 数据并写入用户缓存；
- `train.py` 依赖 CUDA、NVIDIA GPU、PyTorch 2.9.1 和专用 kernel；
- Prompt 评测的完整路径需要模型 API 与 API Key；
- 原仓库的自主循环包含分支、提交和回退操作，不应替代本项目 Harness。

实际代码级复用来自 `alternative-frame/v0.1`：

- `DomainAdapter`、`Plan`、`SubTask`；
- `ToolRegistry`、`ShellRunner`、`ExperimentRunner`；
- `HarnessPreflightChecker`；
- `AcceptanceContract` 和既有证据字段。

### 12.2 方法论适配

| `autoresearch` 模式 | 第一阶段适配 |
| --- | --- |
| 固定数据与评测函数 | 固定数据版本、种子、划分和 accuracy |
| baseline 先行 | 首个真实实验只运行最近类中心 baseline |
| 固定命令执行实验 | `ExperimentRunner` 执行明确的 Python 命令 |
| 从输出解析指标 | 标准输出 `accuracy=...` 进入工具 metadata |
| 保存实验结果 | 写入 `artifacts/baseline_metrics.json` |
| 失败不伪装成功 | 非零退出码或缺少预期文件均返回失败 |
| 按 Run ID 保存历史 | 当前未实现；后续交给现有 `LongHorizonStore`，不另建存储框架 |
| baseline/改进比较 | baseline 使用 `x1`，improved 使用 `x1+x2`，由 `MetricComparator` 读取 JSON 比较 |
| Prompt 评测 | 禁用；完整路径需要模型 API 和 API Key |
| GPU 训练 | 禁用；原实现需要 CUDA、NVIDIA GPU 和联网准备数据 |

### 12.3 许可证结论

`autoresearch-master/README.md` 声明项目许可证为 MIT，但审计目录根部没有独立的
`LICENSE`、`COPYING` 或 `NOTICE` 文件。当前第一阶段没有复制、抽取或导入其代码、
数据格式或资源，因此没有引入需要随代码保留的第三方版权头。若后续决定复制任何
实现，必须先取得完整 MIT 许可证文本并按许可证要求保留版权与许可声明。

### 12.4 第一阶段数据流

```text
generate_dataset
       |
inspect_dataset
       |
run_baseline
```

第二阶段在上述数据流后增加：

```text
run_baseline -----+
                  +--> compare_experiments --> build_initial_report
run_improved -----+                              |
                                                 v
                                  global gate rejects missing verification
                                                 |
                                      verify_best --> update_research_report
                                                 |
                                           completed
```

真实固定结果为 baseline `0.80`、improved `0.95`、独立复验 `0.95`。
