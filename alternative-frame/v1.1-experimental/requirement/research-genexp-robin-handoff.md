# 科研 Demo 成员交接任务书：GenExp + robin

## 1. 任务归属

- 负责板块：科研 Demo
- 参考项目：`GenExp`、`robin`
- 建议开发分支：`feature/research-genexp-robin`
- 集成目标：`integration/v1.1-experimental`
- 基线：从队长指定的 v1.1-experimental 基线创建分支。开始工作前必须记录基线 commit；不得直接从个人旧分支继续开发。

## 2. 目标

把两个科研领域项目的可取设计接入科研 Demo：

1. GenExp：把科研流程扩展为“假设生成 -> 候选筛选 -> 实验协议 -> 结果记录”的结构化产物链。
2. robin：对多个候选假设或实验协议进行独立评价、pairwise ranking 和最佳候选选择。

这项任务是科研领域插件开发，不修改通用编排器，也不把 Prolog/Aleph 或 Edison 平台变成核心依赖。

## 3. 允许修改范围

允许修改：

- `domains/research_demo.py`
- `domains/research_tools/`
- 科研 Demo 对应的 `examples/`、`prompts/` 和专项测试
- 本任务书对应的依赖和许可证记录

未经队长审核不得修改：

- `core/orchestrator.py`
- `core/long_horizon/controller.py`
- `core/long_horizon/state.py`
- 公共事件名称、合同字段和既有产物路径
- `v1.0` 基线目录

如果必须修改公共接口，先提交接口变更说明和兼容性测试，等待审核后再编码。

## 4. 最小接口

建议提供独立领域接口，名称可以调整，但输入输出必须结构化：

```python
generate_hypotheses(context) -> list[dict]
rank_candidates(candidates, evidence=None) -> list[dict]
build_protocol(hypothesis) -> dict
```

每个产物必须包含：`id`、`source`、`status`、`created_by`、`metadata`。模型文本只能作为候选内容，最终排名必须有可检查的评分字段和评价依据。

## 5. 必须完成的功能

- 至少生成两个可比较的科研候选。
- 对候选进行独立评分，不能只按生成顺序选择第一项。
- 输出结构化假设文件、候选排名文件和实验协议文件。
- 将产物纳入现有 artifact/manifest 和合同验收链路。
- 候选评价失败时返回结构化失败结果，不得伪造排名。
- 默认离线可运行；真实 API 只能作为可选模型入口。
- 固定随机种子后，离线候选和排名结果可复现。

## 6. 依赖和许可证

- `GenExp` 根目录为 MIT，但嵌套 `amiga-master` 等组件要单独核对许可证。
- `robin` 为 Apache-2.0；复制代码时保留版权、许可证和 NOTICE 要求。
- 优先只借鉴协议和流程，不直接复制外部平台适配代码。
- 新增依赖必须写入依赖清单，并说明是否为运行必需依赖。

## 7. 验收命令

在干净工作区执行并保存完整输出：

```powershell
python -m pytest -q tests/test_research_demo.py
python -m pytest -q tests/test_research_genexp_robin.py
python run_research_demo.py
python validate_contribution.py --domain research
```

如果仓库入口参数与上述命令不同，必须在交付说明中给出实际命令，不能只发截图。

最低验收证据：

- 假设、排名、协议和最终报告的实际文件路径；
- 候选数量和每个候选的评分；
- 运行 ID、事件日志和产物 manifest；
- 正常场景及一次评价失败/重试场景；
- 测试通过数字和退出码。

## 8. 交付格式

提交一个或多个聚焦 commit，提交信息建议：

```text
feat(research): add hypothesis protocol and candidate ranking plugin
```

汇报必须包含：基线 commit、分支名、改动文件、依赖、许可证、运行命令、测试结果、产物路径、已知限制和回退 commit。不得提交 `runs/`、`.pytest_cache/`、`__pycache__/`、API Key 或外部平台凭据。
