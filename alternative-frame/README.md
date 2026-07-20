# Alternative Frame

通用 Harness Runtime 的独立开发目录。

本目录的目标不是再实现一套科研框架，而是把现有 `autoresearch-master` 中可以跨领域复用的机制抽象出来，形成同一套运行时，并通过科研与软件工程两个领域能力包验证泛化性。

## 当前目录约定

```text
alternative-frame/
├── v0.1/          # 唯一当前开发版本：模型配置、编排器、baseline、UI 和 Demo
├── docs/          # 架构文档、比赛材料、文档生成工具和参考图
├── archive/v0.0/  # 早期重复实现和旧 UI，仅作历史留档
├── src/           # 预留：下一阶段从 v0.1 抽出的通用运行时源码
└── app/           # 预留：下一阶段的统一启动入口
```

当前请只使用 `v0.1`，不要再在根目录维护第二份 `core/`、`domains/` 或 `ui`。

## 当前设计共识

核心结论：

> 实验循环引擎 + Git 回滚 + 多维自评 + API 客户端 = 通用骨架；替换 `prepare -> evaluate -> config` 三层即可适配任意领域。

## 目录规划

```text
alternative-frame/
├── core/                 # Tier 1：完全通用的运行时内核
│   ├── loop/             # 任务/实验循环、状态、超时与恢复
│   ├── rollback/         # 可恢复的版本与 checkpoint 管理
│   ├── eval/             # 多维评估协议、指标和结果存储
│   └── api/              # 模型/API 抽象、重试和限流
├── adapters/             # Tier 3：领域适配接口
│   ├── dataset/          # 数据/代码仓库/任务输入加载
│   ├── evaluator/        # 领域验收器适配
│   └── config/           # 可编辑配置和权限声明
├── domains/              # 领域能力包
│   ├── autoresearch/     # 科研实验领域
│   └── software_engineering/ # 软件工程交付领域
├── docs/                 # 架构、协议、决策和实验记录
└── tests/                # 通用内核和领域适配测试
```

## Tier 分层

### Tier 1：完全通用

- 结果记录与结构化存储
- Git/版本回滚抽象
- 多维评估框架
- 任务状态、日志和基础指标

### Tier 2：高度可复用

- 实验/任务循环引擎
- LLM API 客户端基类
- 重试、限流、超时和崩溃保护
- stdout/日志到结构化指标的解析

### Tier 3：通过接口适配

- 数据准备：科研数据集、代码仓库、需求文档
- 评估器：科研指标、测试结果、代码质量、安全扫描
- 可编辑配置：训练配置、编译参数、Lint 规则、测试框架参数

### Tier 4：领域特化

- 科研：模型训练循环、实验指标、研究报告和多轮研究场景
- 软件工程：需求拆解、代码修改、测试修复、构建与交付

## 设计原则

1. 通用内核不导入科研领域对象，例如 `train.py`、`val_bpb` 或论文场景。
2. 领域差异必须通过协议、配置和适配器表达，而不是复制一套 loop。
3. Git 回滚必须是可注入的策略，默认使用安全 ref/checkpoint；领域适配器不直接执行破坏性 reset。
4. 评估器返回结构化结果和证据，不只返回一个浮点分数。
5. 每个任务都必须能暂停、恢复、回放，并保留决策和产物轨迹。
6. 软件工程 Demo 必须与科研 Demo 共享 Runtime 代码，才能证明泛化性。

## 参考资料

设计草图归档于 [`docs/references/`](docs/references/)。

## 运行交互 UI v0

在本目录执行：

```powershell
python ui_v0.py
```

UI v0 直接调用当前 `PlanningPipeline + MainAgent + Orchestrator`，支持输入自然语言目标、自动识别科研/软件工程领域、生成任务 DAG、并行运行子 Agent，并在界面中查看子任务状态、尝试次数、产物和运行日志。
