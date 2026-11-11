# Alternative-Frame v1.1-experimental

## 最新插件版与成员获取方式

当前共享分支为 `codex/v1.1-optional-plugins`。主界面启动 `python ui.py`，或在 Windows 双击本目录的 `启动长程任务UI.bat`。需要 Python 3.10+ 与 tkinter；运行测试另需 pytest。

主界面支持按需勾选 BM25 运行记忆、依赖消息、SQLite 执行队列和用量交叉审计，适用于真实 API 的标准多 Agent 与长程任务，默认关闭。操作见 [插件说明](docs/OPTIONAL_PLUGINS.md)，版本、验证和获取步骤见 [本轮共享交接](docs/GITHUB_HANDOFF_20261111.md)。

`ui_v1_1.py` 是独立组件实验控制台；日常任务和插件接入请使用 `ui.py`。

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
