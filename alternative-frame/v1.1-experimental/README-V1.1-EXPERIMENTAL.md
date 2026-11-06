# Alternative-Frame v1.1-experimental

这是一个与 `v1.0` 并列的试验副本。启动脚本和原有 Demo 保持可用；新增能力集中在 `core/experimental/`，可单独导入、测试和删除。

2026-11-06 更新：主界面 `ui.py` 现已提供“选择插件…”入口，可分别勾选 BM25 运行记忆、依赖消息、SQLite 执行队列和用量交叉审计。适用于 API 模型的标准多 Agent / 长程任务，默认全部关闭，恢复时沿用已保存配置。详见 `docs/OPTIONAL_PLUGINS.md`。这与下方独立实验控制台是不同入口；主界面选择会真正参与任务执行。

建议先运行 `python -m pytest -q tests/test_experimental_runtime.py tests/test_plugin_integration.py`，再运行全量 `python -m pytest -q`。插件 OFF/ON 效果仍需同条件真实实验，不能从组件测试推出能力提升。

试验重点是四个具体问题：如何统一外部服务接口、如何在真实 API 缺少 usage 时提供预算护栏、如何给多 Agent 任务提供租约和恢复、如何在不强制绑定向量数据库的情况下改进记忆检索。

## v1.1 独立 UI

运行 `python ui_v1_1.py` 打开独立实验控制台。它与继承自 v1.0 的 `ui.py` 分开，提供成本对账、任务入队/认领/ACK、有界消息发送、记忆检索、事件审计和离线组合演示。默认所有操作写入临时本地目录，不调用外部 API。
