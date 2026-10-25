# 评测成员交接任务书：science-sandbox Oracle

## 1. 任务归属

- 负责板块：统一评测 / D 成员评测线
- 参考项目：`science-sandbox`
- 建议开发分支：`feature/evaluation-science-sandbox`
- 历史评测分支：`feature/d-benchmark`，仅作为历史参考；不得直接覆盖其已冻结内容
- 集成目标：`integration/v1.1-experimental`
- 基线：从队长指定的 v1.1-experimental 基线创建分支，并记录 commit。

## 2. 目标

把 science-sandbox 的 Oracle、sealed harness、隐藏评测集和 one-shot/long-horizon 对比思想接入统一评测层，评价科研 Demo、软件 Demo 和端边云运行时的真实完成质量。

评测器必须与 Agent 执行逻辑分离。Agent 可以获得评分反馈，但不能读取隐藏规则、隐藏测试集身份或标准答案。

## 3. 允许修改范围

允许修改：

- `validation/`
- `reports/`
- 评测专用 `tests/`、`examples/` 和 benchmark manifest
- 与科研/软件/端边云对接所需的只读消费适配器

未经审核不得修改：

- 三个 Demo 的业务实现
- `core/orchestrator.py`、`core/long_horizon/controller.py`
- 公共合同字段和事件名称
- `v1.0` 基线目录

## 4. 必须完成的功能

- 定义隐藏评测集或隐藏规则，Agent 运行时不能直接读取。
- 提供独立 Oracle，根据工具调用、产物、指标和证据计算评分。
- 支持至少三类对比：one-shot、multi-step、long-horizon。
- 能消费科研、软件和端边云的统一运行 manifest、state 和 events。
- 输出原始 JSONL、汇总 JSON、CSV 或 Markdown 报告。
- 评测结果必须可复现，固定输入和 seed 时结果一致。
- 评测失败要区分“被测系统失败”和“评测器配置错误”。

## 5. 软件 Demo 配合要求

软件 Demo 成员不负责移植 science-sandbox，但必须提供：

- 稳定的运行 manifest；
- 关键产物和测试退出码；
- 正常、retry-once、local-recovery 三类场景的运行记录；
- 不暴露隐藏测试集内容的评测输入接口。

评测成员只能消费这些稳定接口，不应直接修改软件 Demo 逻辑。

## 6. 许可证和数据边界

- `science-sandbox` 根目录为 MIT。
- README 明确说明部分 Malinois 模型权重受 boda2 license 约束。
- 可以借鉴 harness/oracle 代码和设计，但不要复制受限制模型权重、数据集或结果文件。
- 所有隐藏评测数据必须记录来源、许可证和是否允许进入比赛仓库。

## 7. 验收命令

```powershell
python -m pytest -q tests/test_evaluation*.py
python validate_contribution.py --domain evaluation
python evaluation_smoke.py
```

如果入口名称不同，交付时必须提供实际可运行命令。最低验收证据：

- Agent 无法直接读取隐藏规则的测试；
- Oracle 能拒绝伪造的 Agent 文本声明；
- 科研、软件、端边云各至少有一个真实运行样例；
- one-shot、multi-step、long-horizon 的对比报告；
- 原始 JSONL、汇总文件、运行 ID 和退出码。

## 8. 交付格式

建议提交信息：

```text
feat(evaluation): add sealed oracle benchmark for cross-domain runs
```

交付报告必须包含基线 commit、分支、改动文件、隐藏数据清单、许可证、测试命令、测试结果、样例报告和已知限制。不得提交 `.pytest_cache/`、`__pycache__/`、临时运行目录或任何真实 API 密钥。
