# 软件工程 Demo 协作接口约定 v0.1

状态：已冻结  
适用版本：`alternative-frame/v0.1`  
适用范围：软件工程最小闭环 Demo 及其与通用 Harness 的集成

## 1. 文档目的

本文件用于约定软件工程 Demo 与通用 Harness 之间的交接方式，使框架负责人和 Demo 负责人可以并行开发。

“接口冻结”不代表永远不能修改，而是：开发期间默认遵守本文件；确需修改公共接口时，先沟通、记录变更，再升级接口版本。

软件工程 Demo 必须复用项目现有的任务模型、编排器、Agent 结果模型、工具系统和验收器，不能独立实现另一套 Agent 框架。

## 2. 责任边界

### 2.1 框架负责人

主要负责：

- `v0.1/core/`
- Main Agent 与 Orchestrator
- `Plan`、`SubTask`、`AgentResult` 数据结构
- ToolCallingAgent 与模型 API
- FileEditor、ShellRunner、TestRunner、GitClient
- AcceptanceEvaluator
- UI、运行指标、长程控制和状态恢复

### 2.2 软件 Demo 负责人

主要负责：

- 软件工程示例项目
- 冻结的需求文档
- 软件任务 DAG
- 软件角色提示词
- 自动化测试和边界测试
- 软件领域验收配置
- 软件 Demo 启动入口
- Demo 使用说明和运行报告样例

### 2.3 修改限制

- Demo 负责人原则上不直接大幅修改 `v0.1/core/`。
- 如果现有公共接口不能满足需要，先提交接口需求，说明使用场景、期望输入、期望输出和影响范围。
- 软件领域专用逻辑放在 `domains/`、`examples/` 或 `prompts/`，不要写进通用核心。
- 框架负责人修改公共接口后，应通知 Demo 负责人同步最新代码。

## 3. 冻结目录结构

软件 Demo 使用以下目录和文件：

```text
alternative-frame/v0.1/
├── domains/
│   └── software_demo.py
├── examples/
│   └── software_task/
│       ├── README.md
│       ├── requirements.md
│       ├── acceptance.json
│       ├── src/
│       ├── tests/
│       └── expected/
├── prompts/
│   └── software/
│       ├── analyst.md
│       ├── architect.md
│       ├── tester.md
│       ├── developer.md
│       └── reviewer.md
├── tests/
│   └── test_software_demo.py
└── run_software_demo.py
```

约定：

- 示例项目只能在自己的 workspace 范围内被修改。
- `expected/` 可保存参考结果或隐藏验收说明，但模型运行时不应读取答案文件。
- API Key、真实密钥和个人配置不得写入以上目录或 Git。

## 4. 启动接口

统一启动文件为：

```text
alternative-frame/v0.1/run_software_demo.py
```

最小启动命令：

```powershell
cd "E:\Users\wang\Documents\plan a project\alternative-frame\v0.1"
python run_software_demo.py
```

后续可以增加参数，但无参数启动必须有清晰行为，例如使用本地 Stub 或提示缺少模型配置，不能静默失败。

## 5. Plan 输入输出接口

`domains/software_demo.py` 必须提供以下函数：

```python
from core.models import Plan


def build_software_plan(goal: str, workspace: str) -> Plan:
    """根据用户目标和示例工作区生成软件工程任务 DAG。"""
```

输入含义：

- `goal`：用户自然语言目标。
- `workspace`：软件 Demo 工作区路径。

输出必须使用现有 `core.models.Plan`，不能返回自定义字典或另一套任务类。

当前真实字段为：

```python
Plan(
    goal="实现任务管理服务并通过全部测试",
    subtasks=[...],
    final_acceptance=["tests_pass", "review_complete"],
)
```

## 6. SubTask 接口

所有软件子任务必须使用现有 `core.models.SubTask`：

```python
SubTask(
    id="implementation",
    role="developer",
    description="根据需求、设计和测试实现功能",
    depends_on=["architecture", "tests"],
    inputs=["requirements.md"],
    acceptance=["tests_pass"],
    max_retries=2,
    metadata={
        "workspace": "examples/software_task",
        "expected_outputs": ["src/task_service/service.py"],
        "checks": [],
    },
)
```

固定要求：

- `id` 在同一个 Plan 中必须唯一。
- `role` 使用注册表中已注册的角色名称。
- `depends_on` 只能引用同一个 Plan 中已存在的任务。
- DAG 不允许循环依赖。
- 工作区、验收检查和预期产物放入 `metadata`，当前不修改 `SubTask` 公共字段。

建议的最小软件任务 DAG：

```text
requirements
├── architecture
└── tests
      ↓
implementation
      ↓
integration
      ↓
review
```

`architecture` 与 `tests` 可以并行；`implementation` 必须等待二者完成。

## 7. AgentResult 接口

所有 Agent 必须返回现有 `core.models.AgentResult`：

```python
AgentResult(
    subtask_id="implementation",
    status="success",
    summary="已实现任务管理服务并完成测试",
    artifacts=["src/task_service/service.py"],
    evidence=["tool=test_runner;success=True"],
    failures=[],
)
```

字段约定：

- `status` 只能表达真实执行状态，主要使用 `success`、`failed`、`timeout`。
- `summary` 是说明文字，不能单独作为成功证据。
- `artifacts` 保存实际产物的相对路径。
- `evidence` 保存真实工具执行、测试和验收证据。
- `failures` 保存机器可识别的失败原因。
- 模型口头声称“测试通过”不能代替 TestRunner 或 ShellRunner 的执行证据。

## 8. 工具接口

软件 Demo 优先使用现有工具：

| 角色 | 允许使用的工具 |
|---|---|
| analyst | FileEditor（以读取为主） |
| architect | FileEditor（以读取和文档输出为主） |
| tester | FileEditor、ShellRunner、TestRunner |
| developer | FileEditor、ShellRunner、TestRunner、GitClient |
| reviewer | FileEditor、TestRunner、GitClient |

安全要求：

- 所有文件操作必须限制在软件 Demo workspace 内。
- 不直接使用任意绝对路径写文件。
- 不执行删除工作区、格式化磁盘、强制重置仓库等破坏性命令。
- 不使用 `git reset --hard`。
- 不将 API Key 写入代码、日志、报告或测试数据。
- 如需新增工具，优先扩展 `ToolRegistry`，不要绕过工具系统直接执行。

## 9. 验收接口

软件 Demo 的成功必须由机器可检查的事实决定，至少包括：

1. 必需产物存在；
2. 自动化测试真实执行；
3. 测试命令退出码为 0；
4. Reviewer 完成最终检查。

`acceptance.json` 建议结构：

```json
{
  "checks": [
    {
      "id": "service_exists",
      "check_type": "file_exists",
      "path": "src/task_service/service.py"
    },
    {
      "id": "tests_pass",
      "check_type": "command",
      "command": "python -m unittest discover -s tests -v"
    }
  ]
}
```

映射到 `SubTask.metadata` 时使用当前 AcceptanceEvaluator 支持的格式：

```python
metadata={
    "expected_outputs": ["src/task_service/service.py"],
    "checks": [
        {
            "id": "service_exists",
            "check_type": "file_exists",
        },
        {
            "id": "tests_pass",
            "check_type": "command",
            "command": "python -m unittest discover -s tests -v",
        },
    ],
}
```

注意：当前 `AcceptanceEvaluator` 的 `file_exists` 检查读取 `metadata.expected_outputs`，不是直接读取单个 check 的 `path`。在公共验收接口升级前，Demo 必须遵守这个现状。

## 10. 软件 Demo 最小交付标准

Demo 负责人提交时必须满足：

- [ ] `python run_software_demo.py` 可以启动；
- [ ] 包含冻结的自然语言需求；
- [ ] 包含真实的待实现代码或确定性缺陷；
- [ ] 包含正常路径和边界条件测试；
- [ ] 初始版本至少有一个确定失败的测试；
- [ ] Agent 能读取和修改真实文件；
- [ ] Agent 能执行真实测试；
- [ ] 测试失败后能够再次修改并重试；
- [ ] 最终成功由 AcceptanceEvaluator 和真实证据判断；
- [ ] 输出修改文件、测试结果、耗时和重试次数；
- [ ] 生成 JSON 或 Markdown 运行报告；
- [ ] README 包含全新环境复现步骤；
- [ ] 不包含任何真实 API Key；
- [ ] 不在 Demo 内实现第二套 Orchestrator 或 Agent 数据模型。

## 11. 集成验收

框架负责人合并 Demo 前检查：

- 是否使用同一个 `Orchestrator`；
- 是否使用现有 `Plan`、`SubTask`、`AgentResult`；
- 是否使用同一个 `ToolRegistry`；
- 是否由 `AcceptanceEvaluator` 判断成功；
- 是否能进入统一日志、指标系统和 UI；
- 是否将所有文件和命令限制在声明的 workspace；
- 是否可以在 Stub 模式和真实 API 模式下使用同一任务定义；
- 是否保留了失败和重试的真实证据。

## 12. Git 协作约定

建议软件 Demo 负责人使用独立分支：

```text
feature/software-demo
```

提交建议按小步骤进行：

```text
feat: add software demo workspace
test: add software demo acceptance tests
feat: add software task plan
docs: add software demo run guide
```

禁止提交：

- `.env` 和 API Key；
- `__pycache__/`；
- `.pytest_cache/`；
- 大量临时日志；
- 与软件 Demo 无关的个人文件。

合并前应由至少一名队员审查，并运行软件 Demo 的自动化测试。

## 13. 接口变更流程

发现接口不足时，按以下流程处理：

1. 在群内或 Issue 中说明当前问题；
2. 给出希望增加或修改的字段/函数；
3. 说明为什么不能通过现有 `metadata`、工具或领域适配器解决；
4. 框架负责人判断是否属于通用能力；
5. 通用能力由框架负责人修改 `core/` 并补测试；
6. 更新本文件并记录版本变化；
7. Demo 负责人同步最新主分支后继续开发。

接口版本规则：

- 文案澄清、示例补充：仍为 `v0.1`；
- 新增兼容字段或可选能力：升级为 `v0.2`；
- 删除字段或产生不兼容变化：升级为 `v1.0`，并提供迁移说明。

## 14. 当前已知限制

- 当前 `AcceptanceEvaluator` 的工具证据仍较粗，只能识别部分字符串证据。
- `GitClient` 尚未完整实现安全 commit/checkpoint/restore。
- 真实模型是否返回标准 OpenAI `tool_calls` 仍需使用实际 API 验证。
- 当前 Orchestrator 主要执行静态 DAG，尚未完整支持全局动态重规划。
- 这些限制由框架负责人处理，不要求软件 Demo 负责人另写一套替代实现。

## 15. 一句话协作原则

> 软件 Demo 负责人交付领域任务、代码、测试和验收；框架负责人交付统一运行时。双方通过本文件定义的 Plan、SubTask、AgentResult、工具和验收接口连接。
