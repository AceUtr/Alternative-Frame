# Alternative Frame v0.1

这是当前多 Agent Harness v0 的冻结副本，并增加了“用户自定义 API 模型”的能力。

## 默认本地 Demo

不需要 API Key：

```powershell
cd "E:\Users\wang\Documents\plan a project\alternative-frame\v0.1"
python run_demo.py
```

## 使用用户指定的模型

v0.1 中 Main Agent 和所有子 Agent 默认共享用户配置的同一个强模型；角色通过不同系统提示词、任务上下文和未来的工具权限形成差异。

```powershell
$env:MODEL_BASE_URL = "https://api.openai.com/v1"
$env:MODEL_API_KEY = "your-api-key"
$env:MODEL_NAME = "your-model-name"
python run_api_demo.py
```

## 运行适配版 UI

```powershell
python ui.py
```

UI 支持在“本地 Stub”和“API 模型”之间切换，并可填写 Base URL、API Key、模型名称、Temperature 和 Max Tokens。可先使用“测试连接”验证配置，再用同一个用户指定模型驱动主 Agent 和全部角色子 Agent。API Key 仅保存在窗口内存中。

该接口是 OpenAI-compatible 形式，因此可用于兼容该协议的主流模型服务。真实 API Key 只通过环境变量传入，不写入代码和日志。

## v0.1 当前边界

- 已实现：模型配置、OpenAI-compatible Chat API 客户端、主/子 Agent 共享同一模型、角色提示词隔离、API 失败结构化返回。
- 已实现：`FileEditor`、`ShellRunner`、`TestRunner`、`GitClient`、`ExperimentRunner`、`ToolRegistry` 和 `ToolCallingAgent` 第一版。
- 已保留：本地 stub、任务规划、任务 DAG、并行编排、重试、科研与软件工程模板、UI v0。
- 尚未完成：把工具调用循环和工具权限接入 UI、真实任务工作区、记忆、动态拓扑和端边云调度。

工具层已具备接口和本地执行实现；要在 UI 中启用真实工具调用，还需要把 API 模型返回的 tool call 与角色权限配置接入 `ui.py`，并在真实 workspace 中执行软件工程/科研任务。

## 运行 baseline 与指标记录

```powershell
python run_baseline.py
Get-Content runs\results.jsonl
```

这会分别运行科研和软件工程的 stub baseline，并记录任务数、成功数、轮次、重试次数、耗时、模型调用数和人工干预次数。审计结论见 [`docs/code-audit-v0.1.md`](docs/code-audit-v0.1.md)。当前结果明确标记为 `orchestration_only`，不会冒充真实科研/软件交付结果。

## 运行长程控制器 MVP

```powershell
python run_long_horizon_demo.py
```

该离线 Demo 会执行两个阶段：第一阶段完成实现，随后全局评估器发现仍缺少独立验证，Replanner 自动生成第二阶段测试与审查任务。状态保存在 `runs/long_horizon/<run_id>/state.json`，事件轨迹保存在同目录的 `events.jsonl`。

如果当前环境不允许写入项目 `runs/` 目录，可显式指定状态目录：

```powershell
$env:LONG_HORIZON_RUNS_DIR = "$env:TEMP\alternative-frame-long-horizon"
python run_long_horizon_demo.py
```

实现与边界说明见 [`docs/milestone-3-long-horizon-mvp.md`](docs/milestone-3-long-horizon-mvp.md)。

UI 的任务模式默认提供“标准多 Agent”和“长程任务”。“工具调用自检”和“失败修复自检”作为开发诊断能力保留在“开发者模式”中，不进入默认比赛演示流程。

API 模式下，长程任务的后续阶段由 `StructuredReplanner` 生成严格 JSON DAG，并在执行前校验角色、工具权限、路径、依赖、循环和剩余预算。本地 Stub 模式使用规则型恢复计划，确保离线可演示。

API 长程模式使用 `StructuredGlobalEvaluator` 判断最终目标：必需文件要有本次运行的产物来源，测试命令必须精确匹配且退出码为 0，硬证据全部通过后才允许模型进行语义覆盖判断。模型返回无效或 API 不可用时采用 fail-closed，不会把任务误判为完成。详见 [`docs/milestone-4-global-completion.md`](docs/milestone-4-global-completion.md)。

执行 API 长程任务前，`StructuredGoalContractGenerator` 会先从原始用户目标生成严格 JSON 验收合同。`ContractValidator` 校验必需条件、类型、相对路径、安全命令和指标阈值；合同连续两次不合法时会在任何 Agent 或工具执行前终止。合同会写入长程 `state.json`。详见 [`docs/milestone-5-goal-contract-generator.md`](docs/milestone-5-goal-contract-generator.md)。

API 与本地 Stub 的长程模式都会在执行前弹出合同预览窗口。用户可以确认、取消，或编辑完整 JSON；编辑后必须重新通过原始目标、相对路径和安全命令校验。取消任务不会启动 LongHorizonController、子 Agent 或工具。标准单阶段多 Agent 模式暂不强制确认合同。

合同确认后，`ContractAwarePlanner` 会根据合同重新构建初始 DAG，并要求每条必需标准都映射到具体负责的任务和检查；合同覆盖不完整、角色越权或路径不安全时不会开始执行。

长程模式现支持阶段边界安全暂停、持久化恢复和运行历史窗口。暂停不会强杀正在执行的 Agent，而是在当前阶段结束并保存证据后停止。恢复时加载冻结的目标、合同、阶段记录和 pending plan。详见 [`docs/milestone-6-contract-planning-resume.md`](docs/milestone-6-contract-planning-resume.md)。

真实模型两阶段验收可运行 `python run_real_two_phase_demo.py`。该脚本受控遗漏 `FINAL_EVIDENCE.md`，要求 GlobalEvaluator 在第一阶段拒绝完成并触发 StructuredReplanner，最终必须在后续阶段补齐证据才返回成功。API Key 只从环境变量读取且不会落盘。

任务级执行现采用反馈驱动重试：Agent 会收到完整产物路径、工具权限和验收检查；验收失败后，下一次尝试会获得缺失文件、精确测试命令或证据缺口等结构化修复指令。文件验收同时要求本次任务运行的工具产物来源，旧文件不能直接通过。详见 [`docs/milestone-7-feedback-driven-retry.md`](docs/milestone-7-feedback-driven-retry.md)。

长程初始 DAG 现由确认合同直接生成，不再执行固定的软件认证模板。每个标准和文件必须有唯一责任任务，计划不得发明合同外路径；模型计划失败时自动切换规则型合同 DAG。Replanner 支持超时重试、退避和缺失标准驱动的确定性恢复，双重失败时保存为可恢复状态。详见 [`docs/milestone-8-contract-native-dag-resilience.md`](docs/milestone-8-contract-native-dag-resilience.md)。
