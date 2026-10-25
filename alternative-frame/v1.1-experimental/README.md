# Alternative-Frame v1.1-experimental

这是从 `v1.0` 复制出的隔离试验版本。原有运行脚本、Demo 和测试基线保留；新增能力集中在 `core/experimental/`，可以单独测试和评估。

先运行：

```powershell
python -m pytest -q tests/test_experimental_runtime.py
```

再按需运行全量测试：

```powershell
python -m pytest -q
```

新增能力覆盖四个试验方向：Adapter 协议、模型调用预算护栏、有租约的 Agent 任务队列、支持 RRF 的混合记忆检索。详细变更和边界见 `VERSION.md` 与 `README-V1.1-EXPERIMENTAL.md`。
