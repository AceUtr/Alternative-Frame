# Alternative Frame 架构基线

## 1. 从现有项目抽象出的骨架

当前 `autoresearch-master` 的有效闭环是：

```text
领域配置 → Agent 执行 → 运行/评估 → 解析指标 → 记录结果 → keep/discard/crash → 下一轮
```

这条闭环可以保留，但领域名称不应出现在核心实现中。通用化后的闭环为：

```text
TaskSpec
  → Planner/Loop
  → Tool/Agent 执行
  → Evaluator
  → EvaluationResult
  → DecisionPolicy
  → Checkpoint/Rollback
  → Trace/ResultStore
```

## 2. 三个关键协议

### 2.1 TaskSpec

描述目标、约束、可编辑范围、角色、工具、资源预算和验收条件。

```yaml
task_type: software_delivery
goal: build_and_verify_service
editable_paths: [src/**, tests/**, pyproject.toml]
roles: [analyst, architect, developer, tester]
tools: [file_editor, shell, git, test_runner]
acceptance: [requirements_covered, tests_pass, build_pass]
budget:
  max_steps: 100
  max_tokens: 100000
```

### 2.2 EvaluationResult

```python
EvaluationResult(
    passed: bool,
    score: float | None,
    checks: list[CheckResult],
    evidence: list[ArtifactRef],
    failures: list[Failure],
)
```

科研任务可以将 `val_bpb` 放在 `checks` 中；软件工程任务可以放入测试、构建、安全扫描和需求覆盖率。核心 loop 不感知具体指标。

### 2.3 RollbackPolicy

Git 回滚图中的 `keep / discard / crash` 需要保留语义，但不能让核心层直接写死 `git reset --hard HEAD~1`。建议分成：

- `keep`：创建新的成功 baseline/ref，记录评估结果和产物。
- `discard`：回到本轮开始前的 checkpoint/ref。
- `crash`：保留失败现场、日志和错误证据；是否回滚由策略决定。
- `resume`：从最近一致 checkpoint 继续，不重新执行已完成的幂等步骤。

## 3. 适配层映射

| 现有文件/机制 | 通用抽象 | 科研适配 | 软件工程适配 |
|---|---|---|---|
| `program.md` | `LoopPolicy` | 研究实验循环指令 | 需求-编码-测试循环指令 |
| `prepare.py` | `InputProvider` | 数据集/训练准备 | 克隆仓库/解析需求/建立索引 |
| `train.py` | `MutableArtifact` | 模型和训练代码 | `src/`、测试和配置 |
| `evaluate.py` | `Evaluator` | 指标与研究报告检查 | 测试、构建、安全和文档检查 |
| `api_client.py` | `ModelClient` | 研究 Agent/评审 Agent | 分析、编码、审查 Agent |
| `results.tsv` | `ResultStore` | 实验结果 | 交付结果、质量门禁和回归结果 |
| `run_experiment.sh` | `Runtime` | keep/discard 实验 | 任务 DAG、修复、回归和交付 |

## 4. 软件工程能力包的最小闭环

建议第一个软件工程 Demo 使用中等规模 FastAPI/CLI 服务，完整产物为源码、测试、Dockerfile、API 文档和运行轨迹。

```text
需求解析
→ 验收条件生成
→ 架构设计
→ 任务 DAG
→ 代码与测试生成
→ 执行测试
→ 失败定位
→ 自动修复
→ 回归测试
→ 安全/构建检查
→ 打包交付
```

它应复用通用 `Runtime` 的：

- 任务状态和 checkpoint
- Agent/API 客户端
- 文件变更与 Git 版本管理
- 超时、重试和崩溃保护
- 结构化评估结果
- keep/discard/crash 轨迹

只在领域层新增：角色提示词、工具白名单、测试验收器和软件工程产物规则。

## 5. 第一阶段实现顺序

1. 先实现 `EvaluationResult`、`TaskSpec`、`ResultStore` 数据模型。
2. 把当前 `run_experiment.sh` 的解析、决策和回滚职责拆成 Python 类。
3. 为 Git 回滚增加 dry-run、checkpoint 和失败现场保留，避免核心层使用破坏性 reset。
4. 将科研任务接入新 Runtime，确保迁移前后结果可对比。
5. 增加 `FileEditor`、`ShellRunner`、`GitClient`、`TestRunner` 四个软件工程工具。
6. 实现软件工程验收器，先支持测试通过、构建通过、需求覆盖率三个门禁。
7. 做“同一 Runtime、两种 TaskSpec”的对照演示和代码复用统计。

## 6. 泛化性的验收标准

- `core/` 不包含 `train.py`、`val_bpb`、论文或科研专用概念。
- 切换科研/软件工程时，核心 Runtime 源码不变。
- 两个领域共享同一套 trace、checkpoint、API client、rollback 和 result schema。
- 新增第三个简单领域时，只需实现 `InputProvider`、`Evaluator` 和 `TaskSpec`，不修改 loop。
- 所有 keep/discard/crash/resume 决策均可审计、可回放、可恢复。

