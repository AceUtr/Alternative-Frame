# Alternative-Frame v1.1-experimental

## 定位

这是从 `v1.0` 复制出的隔离试验版本。`v1.0` 是测试基线；本目录用于验证从 7 个开源项目抽取的运行时治理设计。试验版本不会自动替换或修改 `v1.0`。

## 本版本新增

- `core/long_horizon/runtime_changes.py`：按 run ID 和合同修订号校验、归档并串行应用外部追加验收条件；拒绝越界文件路径和过期请求。
- `core/long_horizon/runtime_change_acceptance.py`：由独立本地注入进程驱动主长程控制器的动态合同更新、再验收和阶段重规划，输出带 SHA-256 清单的控制证据。
- `ui.py`：API/Stub 长程任务可在运行时通过“追加运行中要求”提交语义条件或必需产物路径。
- `tests/test_runtime_changes.py`：覆盖完成竞态、合同修订一致性、非法请求和独立进程动态注入。
- `core/experimental/adapters.py`：模型、工具、记忆和事件的最小 Adapter 协议，以及 JSONL 事件日志。
- `core/experimental/cost_guard.py`：请求预留、实际 Token 对账、请求数/Token/美元预算限制。
- `core/experimental/coordination.py`：有界邻居消息总线和 SQLite 任务队列，支持 claim、lease、ACK、释放和过期租约回收。
- `core/experimental/memory.py`：命名空间隔离的 BM25 风格词法检索，可注入向量检索器并用 RRF 融合。
- `tests/test_experimental_runtime.py`：上述模块的边界测试。
- `examples/experimental_runtime_demo.py`：不依赖 API Key 的端到端演示。

## 来源映射

- AutoResearchClaw：Adapter、成本护栏、事件记录和阶段治理思路。
- AutoScientists：队列、claim/lease、ACK、stale claim 回收和协调器写规范日志。
- EvoScientist：中间件式模型调用治理的接口化思路。
- InternAgent：混合检索和 RRF 记忆设计。

本版本实现的是独立的兼容层，没有复制这些仓库的代码。AutoScientists 本地未发现根目录许可证，继续维持设计借鉴状态。

## 验收

在本目录执行：

```text
python -m pytest -q tests/test_experimental_runtime.py
```

全量旧测试仍应作为基线检查执行：

```text
python -m pytest -q
```

## 当前边界

插件治理模块仍是 opt-in 原型；动态运行中需求入口已接入主长程控制器和 `ui.py`。模型 fallback、人工 rubric 门禁、真实向量库和一般 Agent 间分布式网络传输尚未接入。这不是完整自由拓扑群聊；确定性动态变更控制证据也不能替代真实双机、Live API 质量或任意失败条件下的可靠性验收。真实双机只有在不同设备运行同一提交并通过严格 verifier 后才能宣称通过。
