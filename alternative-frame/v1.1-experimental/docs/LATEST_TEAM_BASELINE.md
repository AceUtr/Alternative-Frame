# Latest team baseline

Updated: 2026-11-13 (Asia/Shanghai).
Shared branch: codex/dynamic-fault-recovery.
Repository: https://github.com/AceUtr/Alternative-Frame
Project directory: alternative-frame/v1.1-experimental.

Save existing work before switching branches. For a new checkout:

    git clone --branch codex/dynamic-fault-recovery https://github.com/AceUtr/Alternative-Frame.git
    cd Alternative-Frame/alternative-frame/v1.1-experimental
    python ui.py

Python 3.10+ with tkinter is required. Windows users may double-click 启动长程任务UI.bat. Configure API credentials in the UI; none are shipped.

This branch includes optional runtime plugins and dynamic fault recovery. Implementation commit 831a10b980f0de8bdb6ac4009bc373b66daebbf2 passed 233 tests in the archived local run. This documentation publication is not a new full-test run.

External process termination and runtime requirement changes have controlled local evidence. Real cross-host acceptance and real API A/B remain pending. Edge worker computes SHA-256 only, with no LLM/API inference. The deterministic 311-to-5 result is not real API usage evidence.

Instructions:
- [API A/B task](真实API通信A-B实验任务书.md)
- [Important A/B implementation notes](API_AB_EXECUTION_NOTES.md)
- [Cross-host manual](双机复验操作手册.md)
- [Runtime plugins](OPTIONAL_PLUGINS.md)
- [Fault injection](dynamic-fault-injection.md)
- [Runtime changes](dynamic_runtime_changes.md)

The cross-host ZIP is a separate local delivery, not included in Git. Obtain it from the lead before following that manual. Preserve its fixed commit and configuration.

Create individual branches from this shared branch for new work. Existing competition tags remain unchanged. Secrets, runtime workspaces, caches and historical products are excluded.
