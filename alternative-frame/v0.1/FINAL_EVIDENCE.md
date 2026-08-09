# Final Evidence

- 实现文件：`calculator.py`
  - 提供可由外部代码导入调用的 `add(left, right)` 函数，并返回两个数的加法结果。
- 测试文件：`test_calculator.py`
  - 覆盖正数、负数、零和浮点数加法场景；浮点断言使用 `pytest.approx`。
- 执行命令：`pytest -q`
- 退出码：`0`
- 测试结果：`45 passed in 0.27s`，全部测试通过，无失败。

# Final Evidence

## 软件工程 Demo 状态

- 目标：从一个带缺陷的小型 Python 软件项目出发，完成需求分析、缺陷诊断、代码修复、精确测试、证据报告生成、长程合同验收和恢复演示。
- 当前状态：`software` 贡献门禁通过，默认两阶段 long-horizon demo、local-recovery 场景、UI 离线演示与全量回归均已通过。
- 核心入口：`run_software_demo.py`
- 领域适配器：`domains/software_demo.py`
- 领域 Agent：`domains/software_agents.py`
- 贡献测试：`tests/test_software_demo.py`
- Demo 文档：`docs/software-demo.md`

## 已验证命令

### 贡献门禁

```powershell
python validate_contribution.py --domain software
```

结果：

```text
target=software status=passed
required_files: all 8 required files exist
domain_adapter_preflight: adapter=software; roles=6; tools=3; tasks=6
tests/test_software_demo.py: 6 passed
smoke/run_software_demo.py: exit_code=0
```

最近一次验证报告：

```text
reports/contribution-validation/software-20260809-100513.json
```

### 软件 Demo 负向测试

```powershell
python -m pytest tests/test_software_demo.py -q -p no:cacheprovider
```

结果：

```text
10 passed in 6.47s
```

该测试集覆盖：

- 只有 Agent 文字声称完成但无工具证据时，合同拒绝完成。
- pytest 命令不是精确合同命令时，`pytest_pass` 失败。
- 精确 pytest 命令退出码非 0 时，`pytest_pass` 失败。
- `test_app.py` 存在但缺少本次运行来源时，`regression_tests_exist` 失败。

### 默认两阶段长程 Demo

```powershell
python run_software_demo.py
```

结果：

```text
Status: completed
Phase count: 2

[phase 1] report=success state=incomplete
Missing criteria: software_report_exists

[phase 2] report=success state=accepted
Tasks: build_change_report
Missing criteria: none
```

示例运行证据：

```text
runs/long_horizon/software-demo-20260809-100511/state.json
runs/long_horizon/software-demo-20260809-100511/events.jsonl
examples/software_task/artifacts/software_report.md
```

### 局部 DAG 恢复场景

```powershell
python run_software_demo.py --fault-scenario local-recovery
```

结果：

```text
Status: completed
Phase count: 1
Local recovery cycles: 1
Executed task count: 8
Missing criteria: none
```

用户侧最新运行证据：

```text
runs/long_horizon/software-demo-20260808-235047/state.json
runs/long_horizon/software-demo-20260808-235047/events.jsonl
examples/software_task/artifacts/software_report.md
```

该场景证明：原始完整 DAG 有 6 个任务，注入故障后只额外执行受影响的 2 个节点，而不是重跑全部任务。

### UI 离线演示

```powershell
python ui.py
```

#### 软件 Demo · 两阶段

结果：

```text
PREFLIGHT -> passed | domain=software | checks=7
GLOBAL HARD GATE -> first phase missing software_report_exists
PHASE 2 -> build_change_report
LongHorizonController -> status=completed, phases=2, tasks=6
```

UI 运行证据：

```text
runs/long_horizon/software-demo-20260809-095524/state.json
```

#### 软件 Demo · 局部恢复

结果：

```text
PREFLIGHT -> passed | domain=software | checks=7
LOCAL RECOVERY 1 -> impacted=['run_targeted_tests', 'build_change_report']
LOCAL RECOVERY 1 -> success | remaining=[]
LongHorizonController -> status=completed, phases=1, tasks=8
```

UI 运行证据：

```text
runs/long_horizon/software-demo-20260809-095749/state.json
```

### 共享回归验证

```powershell
python -m pytest tests/test_domain_preflight.py tests/test_end_to_end_harness.py tests/test_orchestrator.py tests/test_local_dag_recovery.py -q
```

结果：

```text
12 passed in 0.52s
```

```powershell
python -m pytest tests/test_metrics.py -q
```

结果：

```text
8 passed in 0.28s
```

```powershell
python -m pytest tests/test_global_evaluator.py::test_resume_revokes_historical_false_completion_and_runs_recovery tests/test_structured_replanner.py::test_structured_replanner_requests_one_correction_after_validation_failure -q
```

结果：

```text
2 passed in 0.81s
```

```powershell
python -m pytest -q
```

结果：

```text
98 passed in 8.14s
```

## 三层恢复证据

### 1. 任务级重试

- 触发位置：`implement_fix`
- 证据：`attempts=2`
- 行为：第一次修复故意产生错误实现，验收器用精确 pytest 命令拒绝；Orchestrator 注入 `retry_feedback` 后第二次修复成功。

### 2. 阶段内局部 DAG 恢复

- 触发命令：`python run_software_demo.py --fault-scenario local-recovery`
- 证据：`Local recovery cycles: 1`
- 冻结节点：
  - `inspect_requirements`
  - `inspect_repository`
  - `diagnose_failure`
  - `implement_fix`
- 恢复节点：
  - `run_targeted_tests`
  - `build_change_report`

### 3. 跨阶段重规划

- 触发命令：`python run_software_demo.py`
- Phase 1：完成修复和测试，但故意缺少 `software_report_exists`
- Global evaluator：拒绝完成并输出 missing criterion
- Phase 2：只运行 `build_change_report`
- 最终状态：`completed`

## 关键产物

- `examples/software_task/app.py`：被修复的软件源码。
- `examples/software_task/test_app.py`：回归测试。
- `examples/software_task/artifacts/requirement_analysis.md`：需求分析证据。
- `examples/software_task/artifacts/architecture_design.md`：结构说明证据。
- `examples/software_task/artifacts/diagnosis.md`：失败基线诊断。
- `examples/software_task/artifacts/software_report.md`：最终软件修复报告。
- `examples/software_task/artifacts/code_diff.patch`：本次运行生成的代码 diff。
- `examples/software_task/artifacts/test_log.txt`：精确测试命令输出。

## 完成度判断

- S1 Domain Adapter / preflight：完成。
- S2 真实工具闭环：完成。
- S3 结构化合同验收：完成。
- S4 两阶段长程闭环：完成。
- S5 三层恢复验证：完成基础演示。
- 共享 Harness、局部恢复和指标基础回归：完成。
- 硬证据负向测试：完成。
- S6 UI 离线演示：完成。
- S6 真实模型接入：后续增强项。

## 当前限制

- 当前软件 Demo 使用确定性本地 Agent，适合离线稳定演示。
- UI 展示与真实模型工具调用接入仍属于后续增强。
- 项目目录当前不是 Git 仓库，因此 `git status` / `git diff --check` 不适用；完成度验证以门禁、测试、state 和 events 证据为准。
