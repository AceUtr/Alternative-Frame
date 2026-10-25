# 多 Agent 编排设计 v0

## 1. 当前状态判断

当前 `autoresearch-master` 是单 Agent 实验循环：

```text
Agent
  → 修改领域文件
  → 调用实验/评估工具
  → 读取指标
  → keep / discard / crash
```

仓库中的 `parallel_eval.py` 虽然使用线程并行运行多个场景，但那些是独立评测任务，不是由一个主 Agent 统筹的子 Agent 协作，因此不能算多 Agent 架构。

## 2. v0 目标

第一阶段只解决四件事：

1. 主 Agent 将高层任务拆成若干有依赖关系的子任务。
2. 子任务可以分配给不同角色的子 Agent。
3. 没有依赖关系的子任务可以并行执行。
4. 主 Agent 汇总子结果，发现失败后重试或重新分配。

暂不实现：

- 长期记忆和记忆压缩
- 动态图拓扑
- 复杂的 Agent 间自由通信
- 学习型路由
- 端边云调度

## 3. 最小角色模型

```text
                    ┌──────────────────┐
                    │    Main Agent    │
                    │  拆解/分配/汇总   │
                    └────────┬─────────┘
                             │
       ┌─────────────────────┼─────────────────────┐
       │                     │                     │
┌──────▼──────┐       ┌──────▼──────┐       ┌──────▼──────┐
│ Researcher  │       │ Experimenter│       │   Reviewer  │
│ 研究/分析    │       │ 执行实验     │       │ 验证结果     │
└─────────────┘       └─────────────┘       └─────────────┘
```

软件工程场景可以复用同一套编排器，只替换角色：

```text
Main Agent
├── Requirement Analyst
├── Architect
├── Developer
├── Test Engineer
└── Reviewer
```

主 Agent 负责协调，子 Agent 只负责自己被分配的子任务，避免第一版出现多个 Agent 互相自由聊天导致状态难以追踪。

## 4. 统一数据结构

### 4.1 SubTask

```python
SubTask(
    id="implement-auth",
    role="developer",
    description="实现 JWT 登录和过期校验",
    depends_on=["design-api"],
    inputs=["artifact://api-design.md"],
    acceptance=["tests_pass", "api_documented"],
    max_retries=2,
)
```

### 4.2 AgentResult

```python
AgentResult(
    subtask_id="implement-auth",
    status="success",  # success / failed / timeout
    summary="已实现登录与 Token 过期校验",
    artifacts=["src/auth.py", "tests/test_auth.py"],
    evidence=["pytest: 12 passed"],
    failures=[],
)
```

### 4.3 Plan

```python
Plan(
    goal="交付一个可测试的 FastAPI 服务",
    subtasks=[...],
    final_acceptance=["all_tests_pass", "build_pass"],
)
```

## 5. 第一版执行流程

```text
1. Main Agent 接收高层目标
2. Main Agent 生成 SubTask DAG
3. Orchestrator 找出所有依赖已满足的 SubTask
4. 并行启动对应角色的子 Agent
5. 收集 AgentResult 和产物
6. 标记已完成任务，解锁下一批任务
7. 失败任务按策略重试、换 Agent 或回报 Main Agent
8. Main Agent 汇总并执行最终验收
```

第一版可以用线程池或 asyncio 实现并行，不需要引入复杂消息队列。

## 6. 研究场景示例

```text
Main Agent：研究一个训练优化方向
│
├── Researcher：分析已有方案        ─┐
├── Baseline Analyst：确认 baseline ─┼─ 并行
└── Experiment Designer：设计实验  ─┘
             │
             ▼
       Experimenter：修改代码并运行实验
             │
             ▼
       Reviewer：检查指标和可复现性
             │
             ▼
       Main Agent：决定保留、回滚或下一轮实验
```

## 7. 软件工程场景示例

```text
Main Agent：实现用户注册服务
│
├── Requirement Analyst：拆解需求和验收条件
├── Architect：设计 API 和数据模型
└── Test Designer：先生成测试用例
             │
             ▼
       Developer：实现代码
             │
             ▼
       Test Engineer：运行测试
             │
       ┌─────┴─────┐
       │           │
    通过         失败
       │           │
       ▼           ▼
    Reviewer   Debugger 修复
       │           │
       └─────┬─────┘
             ▼
       Main Agent：最终验收和交付
```

## 8. 第一阶段必须验证的指标

- 至少 1 个主 Agent 和 3 个子 Agent 正常运行。
- 至少有两批可以并行执行的子任务。
- 子任务结果可以被主 Agent 汇总并作为后续任务输入。
- 子 Agent 失败后可以自动重试，且不会重复执行已成功任务。
- 研究场景与软件工程场景共用同一套 `Orchestrator`、`SubTask` 和 `AgentResult` 数据结构。
- 记录每个子任务的开始时间、结束时间、状态、角色、产物和错误。

## 9. 已实现状态

当前目录已经包含 v0 的可运行实现：

- `core/models.py`：`SubTask`、`AgentResult`、`Plan`。
- `core/agents.py`：`Agent`、`AgentRegistry`、本地 `DeterministicAgent`。
- `core/orchestrator.py`：串行/线程池并行、依赖解锁、重试和结果汇总。
- `core/main_agent.py`：主 Agent 的规划、委派、失败后重新规划入口。
- `domains/presets.py`：科研和软件工程两套角色/任务 DAG。
- `tests/test_orchestrator.py`：并行依赖和循环依赖测试。

运行方式：

```powershell
cd alternative-frame
python run_demo.py
python -m pytest tests
```

当前子 Agent 是确定性本地 stub，用于先验证编排正确性；下一阶段再把 `Agent.run()` 替换为真实 LLM 调用和工具执行。

## 10. 实现顺序

1. 已完成：`SubTask`、`AgentResult`、`Plan` 数据模型。
2. 已完成：串行 `Orchestrator`、依赖校验和循环检测。
3. 已完成：线程池并行执行无依赖任务。
4. 已完成：角色注册表和最小 `Agent` 接口。
5. 已完成：科研场景 Researcher/Experimenter/Reviewer 角色。
6. 已完成：软件工程 Analyst/Architect/Developer/Tester/Reviewer 角色。
7. 已完成基础版：失败重试和主 Agent 重新规划入口。

下一阶段：将确定性 stub 替换为真实 LLM Agent，并增加文件、Shell、Git 和测试工具。

## 10. 重要边界

多 Agent 不等于所有 Agent 同时自由对话。v0 采用“主 Agent 编排 + 子 Agent 执行 + 结构化结果回传”的中心化模式。这样最容易调试、评测和演示；等任务编排稳定后，再增加记忆和动态拓扑通信。
