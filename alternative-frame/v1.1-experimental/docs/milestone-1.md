# 阶段性成果 1：真实验收语义

## 已完成

- API 模型返回文字不再自动等于业务任务成功。
- 新增 `AcceptanceEvaluator`，支持 command、file_exists、metric、manual 四类检查。
- Orchestrator 在子 Agent 返回后执行验收；验收失败会标记 `failed` 并进入重试。
- UI 会展示真实的 `success / failed` 状态，而不是只展示 API 响应是否成功。

## 当前行为

如果软件工程 reviewer 只返回“无法确认测试通过”，而没有真实测试输出：

```text
Agent API 响应：成功
业务验收结果：失败
失败原因：command_not_executed / evidence_missing
```

这是预期行为，因为当前还没有接入真实 `ShellRunner` 和 `TestRunner`，不能虚假宣称软件已经交付。

## 下一阶段接口

要把 `command_not_executed` 变成真实通过，需要接入：

1. `FileEditor`：受限于 workspace 的文件读写和补丁。
2. `ShellRunner`：超时、输出截断、退出码和工作区沙箱。
3. `TestRunner`：pytest/npm 等测试结果结构化解析。
4. `ToolCallingAgent`：模型决定调用工具，读取工具结果后继续循环。

