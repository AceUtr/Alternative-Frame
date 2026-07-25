# D 队员：评测、基准与比赛交付需求书

## 1. 你的身份与最终目标

你是评测与比赛交付 Agent。请协助 D 队员建立统一、可复现、不可伪造的评测体系，用同一套指标衡量科研 Demo、软件工程 Demo 和端边云 Demo，并生成比赛可用的表格、图和演示材料。

你的任务不是只美化 UI，也不是手填几组漂亮数字。所有报告数据必须能追溯到一次真实运行的 `run_id`、状态文件、事件日志、工具记录或指标文件。

## 2. 开工前必须阅读

请先完整阅读：

- `core/metrics.py`
- `run_baseline.py`
- `core/models.py`
- `core/long_horizon/state.py`
- `core/long_horizon/controller.py`
- `core/long_horizon/evidence.py`
- `ui.py` 中运行历史、DAG 和验收证据相关代码
- `docs/code-audit-v0.1.md`
- `docs/milestone-9-local-dag-recovery-visualization.md`

先列出现有日志能直接提供的指标、当前缺失指标、数据来源和采集位置，再开始编码。

## 3. 任务边界

你可以新增或修改：

```text
core/metrics/
benchmarks/
reports/
ui_components/
tests/test_metrics.py
tests/test_benchmark_runner.py
docs/evaluation.md
docs/demo-script.md
run_benchmarks.py
```

注意：当前已有 `core/metrics.py`。若建立 `core/metrics/` 包会产生命名冲突，应优先扩展现有文件或先向队长提交迁移方案，不能同时保留同名模块和包。

不得直接修改研究/软件 Demo 的业务实现来“提高分数”。不得手工更改原始运行结果。不得读取、显示或持久化 API Key。

## 4. 统一指标定义

至少采集并明确计算公式：

| 指标 | 定义 |
|---|---|
| 最终目标完成率 | 通过全部 required 合同条款的运行数 / 总运行数 |
| 子任务成功率 | success 子任务数 / 已执行子任务数 |
| 首次通过率 | 未发生任务重试即通过的任务数 / 已执行子任务数 |
| 重试次数 | 所有 AgentResult 中 `max(attempts - 1, 0)` 之和 |
| 局部恢复次数 | local recovery cycle/event 数量 |
| 跨阶段次数 | 实际 phase 数量，需区分初始阶段与新增阶段 |
| 总耗时 | 从运行开始到最终状态的墙钟时间 |
| 模型调用与 Token | 从模型响应 usage 采集；缺失时标为 unknown，不能记作真实 0 |
| 估算成本 | 根据显式模型价格配置计算；无价格配置时标为 unknown |
| 工具调用成功率 | 成功工具记录数 / 工具调用总数 |
| 人工干预次数 | 合同修改、暂停、人工重跑等定义明确的事件数 |
| 节点分布 | device/edge/cloud 的任务数、耗时和失败数 |

必须区分 `0`、`unknown` 和“不适用”。不得把未采集到的 Token 当作零消耗。

## 5. 必须完成的对照实验

在相同任务、模型、预算、随机种子和工作区初态下，至少支持以下比较：

1. 单 Agent vs 多 Agent。
2. 无恢复 vs 三级恢复（任务重试、局部 DAG、跨阶段 Replan）。
3. 无验收合同 vs 合同驱动验收。
4. 固定执行节点 vs 动态端边云路由（等 C 模块可用后接入）。

每组至少预留多次重复运行能力。测试阶段可用 stub 验证统计管线，但比赛结论必须来自真实模型/真实工具运行，并在报告中标注运行条件。

## 6. 实现步骤

### 阶段 D1：指标 Schema 与采集

- 扩展 `RunMetrics`，但保持旧 `results.jsonl` 可读取。
- 增加 schema version。
- 从 state、events、AgentResult 和 tool_records 中计算指标。
- 写 JSONL 时保持 append-only；坏行不得导致整份历史无法读取。
- 增加敏感字段过滤，至少过滤 key、authorization、token 原文和常见凭证字段。

### 阶段 D2：Benchmark Runner

- 使用明确的 `BenchmarkConfig` 描述任务、模式、重复次数、预算、模型标识和随机种子。
- 每次运行建立独立工作区并重置 fixture，避免上一轮产物污染下一轮。
- 支持失败后继续后续样本，并记录失败原因。
- 输出原始 JSONL 和汇总 JSON/CSV，不覆盖原始数据。

建议目录：

```text
benchmarks/configs/
benchmarks/results/raw/
benchmarks/results/summary/
reports/figures/
```

### 阶段 D3：汇总与可视化

- 生成对照表、成功率图、耗时/成本图和恢复过程统计图。
- 图表标题、轴、图例和单位完整，中文字体不可用时应优雅回退。
- 报告中的每一组聚合结果应保存样本数、均值、中位数和离散程度。
- 小样本不得宣称“显著提升”；仅陈述观察结果和限制。

### 阶段 D4：UI 适配组件

- 在 `ui_components/` 提供可独立导入的指标视图或数据适配器。
- 不直接重写主 `ui.py`；由队长完成最终接线。
- 至少提供运行概览、单次运行详情和对照实验三个数据视图。
- UI 只展示已有数据，不在渲染过程中修改统计结果。

### 阶段 D5：比赛交付材料

`docs/evaluation.md` 必须包含环境、数据集/fixture、模型、预算、重复次数、指标公式、结果和局限性。

`docs/demo-script.md` 应给出 8 到 12 分钟演示脚本，至少覆盖：

```text
目标输入与合同确认
多 Agent DAG 并行执行
真实工具调用与证据
失败重试/局部恢复/跨阶段恢复
科研与软件两个跨领域 Demo
端边云路由
最终验收和指标对比
```

同时准备演示失败时的离线备用材料，但必须标注为历史真实运行回放。

## 7. 测试要求

至少覆盖：

- 指标公式和边界情况正确。
- Token 未提供时为 unknown，而不是 0。
- 旧版 JSONL 可迁移或兼容读取。
- 损坏记录不会破坏其他记录。
- 敏感字段不会进入结果文件。
- 多次 benchmark 的 fixture 相互隔离。
- 聚合结果可由原始记录重新计算得到。

建议验收命令：

```powershell
cd "E:\Users\wang\Documents\plan a project\alternative-frame\v0.1"
python -m pytest tests/test_metrics.py tests/test_benchmark_runner.py -q
python run_benchmarks.py --config benchmarks/configs/smoke.json
```

## 8. 完成标准

- 两个领域使用同一指标 Schema，能横向比较但不混淆领域特有指标。
- 每个汇总数字都能追溯到原始运行记录和 `run_id`。
- 可生成 JSONL、JSON/CSV、图表和评测报告。
- 能明确区分 stub 管线测试与真实模型实验。
- 不泄露 API Key 或请求头。
- 从新环境按文档可复现 smoke benchmark。

## 9. 每次让 AI Agent 工作时的汇报格式

```text
本次完成：
指标定义或公式变更：
修改文件：
数据来源：
测试/benchmark 命令及结果：
生成报告或图表：
未完成、数据不足和风险：
需要队长协调的接口：
```

禁止用模拟数据作为比赛最终结论，禁止只提交界面截图而不提交原始运行证据。
