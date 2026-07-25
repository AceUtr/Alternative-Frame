# Milestone 10: Domain Adapter、启动预检与端到端门禁

## 目标

在科研、软件工程、端边云和评测模块并行开发前，建立统一领域接入边界和执行前检查，避免缺角色、缺工具、非法合同或不可写工作区在长程任务运行中途才暴露。

## 新增能力

### DomainAdapter

`core/domains.py` 定义统一领域适配接口：

```python
register_tools(registry, workspace)
build_agents(model_client, tools)
build_plan(goal)
build_contract(goal)
reset_workspace(workspace)
```

领域实现负责提供能力，核心 Harness 继续负责 DAG 编排、恢复、全局验收和状态持久化。`DomainRegistry` 拒绝重名领域，并提供稳定查询接口。

### HarnessPreflightChecker

`core/preflight.py` 在执行前检查：

- 领域已注册。
- Plan 是合法 DAG。
- 所有任务角色都有 Agent。
- `required_tools` 中的工具全部存在。
- 工作区存在且可写。
- 验收合同合法且目标与计划一致。
- 可选模型连接探针成功。

检查结果使用 `PreflightReport` 和 `PreflightIssue` 返回。正式入口应在创建 LongHorizonController 之前调用 `report.require_ready()`。

## 队员接入方式

每个领域只实现一个 Adapter，并通过已有 `SubTask.metadata` 声明工具和领域扩展信息。不得复制 Orchestrator、LongHorizonController 或验收状态机。

```python
adapter = ResearchDomainAdapter()
domains.register(adapter)
tools, agents = adapter.configure(workspace, model_client)
plan = adapter.build_plan(goal)
contract = adapter.build_contract(goal)

preflight = HarnessPreflightChecker().check(
    domains=domains,
    domain=adapter.name,
    plan=plan,
    agents=agents,
    tools=tools,
    workspace=workspace,
    contract=contract,
    model_probe=model_probe,
)
preflight.require_ready()
```

## 测试门禁

`tests/test_domain_preflight.py` 覆盖领域注册、能力配置、预检成功和缺失能力拦截。

`tests/test_end_to_end_harness.py` 覆盖：

```text
领域适配
→ 启动预检
→ 合同与初始 DAG
→ 首次任务失败
→ 局部 DAG 恢复
→ 下游证据任务
→ 最终完成
→ state.json / events.jsonl 持久化
```

推荐验证命令：

```powershell
python -m pytest tests/test_domain_preflight.py tests/test_end_to_end_harness.py tests/test_orchestrator.py tests/test_local_dag_recovery.py -q
```

若 Windows 报 `.pytest_tmp` 权限错误，应先修复目录 ACL 或在本机选择明确可写的 `--basetemp`。这类 setup error 与业务断言失败必须分开报告。
