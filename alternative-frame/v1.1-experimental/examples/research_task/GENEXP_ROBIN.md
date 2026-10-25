# GenExp + Robin 科研插件

基线：`f1f3520e21ac1229283d8de433b0971a38c713af`，远程分支
`origin/v1.1-experimental`；开发分支：`feature/research-genexp-robin`。

本插件在已有离线分类实验上增加假设、独立候选评价、两两排名和实验协议。
没有修改共享编排器、控制器、状态、公共事件/合同字段、原有产物路径、UI 或
`run_research_demo.py`；其他版本目录保持不变。

## 设计与复用

`inspect_dataset` 使用新的科研领域工具，内部依次完成已有数据检查、假设生成、
候选评价和协议构建。保留原有六项初始任务和两项复验任务，以兼容现有控制器的
任务预算、恢复流程和 UI。

- 两个候选分别使用 x1 和 x1+x2。
- 评价器复用现有最近类中心分类器函数，在训练集做固定种子的分层五折验证。
- 每个候选独立得到五折 accuracy；不读取测试集结果，不采信生成阶段自报分数。
- 两两比较优先选择更高 CV accuracy，其次较少特征；相同条件记录平局。
  排序的最后确定性键是候选 ID，不能据此宣称统计优越性。
- 最佳候选生成带变量、对照、指标、固定命令和约束的协议。
- 原有 baseline/improved 脚本仍真实测量测试集指标，并重新执行观测到的最佳配置。
  候选优先级与观测到的最佳结果允许不同，报告分别记录两者。
- 报告工具会重新检查假设、排名和协议是否与当前训练证据一致，拒绝不一致内容。
- 新产物通过 Adapter 的既有产物白名单、工具记录和四项科研领域 `file_exists`
  条款接入原有合同；没有新增 `check_type`、公共 schema 字段或事件名称。
- 原有 `publish_run_artifacts` 自动收集新产物，manifest 含当前 run_id、大小和 SHA-256。
- 评价失败产生结构化失败文档、空 rankings、空比较结果和 null selected_id，
  并移除旧协议。使用原有任务重试，评价失败与成功两次尝试均留存。

接口位于 `domains/research_tools/discovery.py`：

```python
generate_hypotheses(context) -> list[dict]
rank_candidates(candidates, evidence=None) -> list[dict]
build_protocol(hypothesis) -> dict
```

`rank_candidates` 失败时抛出 `CandidateEvaluationError`，其 `result` 为结构化失败
对象；领域 Tool 将它转换为 `ToolResult(success=False, metadata=...)` 返回既有
调度器。生产代码不应把该异常转换成默认成功排名。

## 新产物

相对于科研 Fixture 的路径：

```text
artifacts/hypotheses.json
artifacts/candidate_rankings.json
artifacts/experimental_protocol.json
artifacts/candidate_evaluation_attempts.json
```

上述 JSON 根对象和候选记录均含 `id`、`source`、`status`、`created_by`、`metadata`。
原报告仍为 `artifacts/research_report.md`，新增假设选择表和新产物链接。
原有指标、图表和复验路径不变。

## 运行与验收

从 `alternative-frame/v1.1-experimental` 执行，默认无需网络或 API：

```powershell
python -m pytest -q tests/test_research_demo.py
python -m pytest -q tests/test_research_genexp_robin.py
python run_research_demo.py
python validate_contribution.py --domain research
```

评价失败后重试演示（环境变量仅是默认关闭的确定性测试故障入口）：

```powershell
$env:RESEARCH_EVALUATION_FAILURES = '1'
try {
    python run_research_demo.py
} finally {
    Remove-Item Env:RESEARCH_EVALUATION_FAILURES -ErrorAction SilentlyContinue
}
```

`candidate_evaluation_attempts.json` 应依次记录 failed、success，第一次失败的 ranking
为空；`events.jsonl` 中应有 `inspect_dataset` 的 `task_retry_scheduled`。

将环境变量设置为 `always` 可验证持续失败不能完成合同；必须随后清除环境变量。
不要把故障场景输出误当成正常运行交付证据。

正常入口输出 run_id 和 published_artifacts。发布目录在
`runs/outputs/research/<run_id>/`，其中有新 JSON、原报告、manifest、state 和 events。
运行状态在 `runs/research/<run_id>/`。验收前在干净的源码工作区运行，保存原始输出；
不要提交这些运行目录或缓存。

## 边界与限制

这是一项受控离线分类任务上的工作流适配，不是生物实验复现、LLM 自主科研或
Robin 的 BTL 排名复现。只有两个预定义特征配置；协议适用于已有 Fixture；没有
加入真实 API 路径。所有 runtime 代码只依赖 Python 标准库，pytest 沿用开发环境。

不重复实现 `core/experimental/` 中的 Adapter/成本治理、队列租约、运行治理或混合
记忆能力。本次没有接入需要它们的新外部服务。

来源和许可证记录：`domains/research_tools/GENEXP_ROBIN_SOURCES.md`。
回退方式：撤销本功能 commit，或在独立工作区检出上述基线 commit；不要重置团队
共享工作区。
