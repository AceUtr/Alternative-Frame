# Alternative-Frame v1.1-experimental

这是一个与 `v1.0` 并列的试验副本。启动脚本和原有 Demo 保持可用；新增能力集中在 `core/experimental/`，可单独导入、测试和删除。

建议先运行 `python -m pytest -q tests/test_experimental_runtime.py`，再运行全量 `python -m pytest -q`。只有在你确认这些模块适合项目方向后，才把其中的接口接入正式运行链路。

试验重点是四个具体问题：如何统一外部服务接口、如何在真实 API 缺少 usage 时提供预算护栏、如何给多 Agent 任务提供租约和恢复、如何在不强制绑定向量数据库的情况下改进记忆检索。

## v1.1 独立 UI

运行 `python ui_v1_1.py` 打开独立实验控制台。它与继承自 v1.0 的 `ui.py` 分开，提供成本对账、任务入队/认领/ACK、有界消息发送、记忆检索、事件审计和离线组合演示。默认所有操作写入临时本地目录，不调用外部 API。
