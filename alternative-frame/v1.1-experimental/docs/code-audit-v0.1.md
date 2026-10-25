# v0.1 代码审计记录

日期：2026-07-18

## 审计结论

v0.1 已具备“领域无关编排骨架”，但当前仍属于 orchestration-only baseline。真实文件修改、Shell、Git、测试和实验工具尚未接入，因此不能把当前 Demo 结果当作比赛最终系统能力。

## 模块审计

| 模块 | 文件 | 状态 | 风险/后续 |
|---|---|---|---|
| 数据模型 | `core/models.py` | 通过 | 需补充 artifact schema 和资源预算 |
| 规划流水线 | `core/planning.py` | 通过 | 当前是规则模板，后续接结构化 LLM 输出 |
| Agent 注册 | `core/agents.py` | 通过 | stub；需接 ToolCallingAgent |
| 主控编排 | `core/main_agent.py`、`core/orchestrator.py` | 通过 | 需加入取消、超时和真实重规划 |
| 模型客户端 | `core/model_client.py` | 初版 | 兼容 Chat API；暂不解析 tool_calls 与 Token 用量 |
| 领域模板 | `domains/presets.py` | 初版 | 只是计划模板，不是真实 Demo |
| 指标记录 | `core/metrics.py` | 初版 | stub Token 为 0；API usage 需接入 |
| UI | `ui_v01.py` | 初版 | 可运行；尚未展示完整指标与真实产物 |

## 已知问题

1. `DeterministicAgent` 会直接返回成功，不能代表真实任务质量。
2. `ConfiguredModelAgent` 目前只调用模型生成文本，尚未执行工具调用。
3. `RunMetrics` 的 Token 字段在 stub 和当前 API Agent 中默认是 0。
4. 真实评估器尚未接入；验收条件目前作为元数据保留。
5. `git`、Shell 和文件编辑没有权限沙箱，需在工具层实现白名单和工作区边界。

## 下一次审计门槛

- 真实软件工程项目可创建/修改文件并运行测试。
- 科研任务可调用现有 autoresearch 实验并解析真实指标。
- API 响应的 usage 能写入 `prompt_tokens/completion_tokens/total_tokens`。
- 至少记录一次失败重试和一次产物回放。

