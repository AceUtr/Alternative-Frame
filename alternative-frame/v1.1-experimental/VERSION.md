# Alternative-Frame v1.1-experimental

## 定位

这是从 `v1.0` 复制出的隔离试验版本。`v1.0` 是测试基线；本目录用于验证从 7 个开源项目抽取的运行时治理设计。试验版本不会自动替换或修改 `v1.0`。

## 本版本新增

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

新增模块目前是 opt-in 原型，尚未接管现有 Orchestrator/UI/Demo 的运行链路；模型 fallback、人工 rubric 门禁、真实向量库和分布式网络传输也尚未接入。这不是完整自由拓扑群聊，也没有声称已经具备真实多设备端边云部署或供应商级账单。应先用单元测试和离线演示评估接口，再决定是否接入现有运行链路。
