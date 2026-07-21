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
