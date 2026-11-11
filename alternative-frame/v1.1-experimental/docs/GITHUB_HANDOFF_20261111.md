# 插件增强版共享交接

整理日期：2026-11-11。共享分支：`codex/v1.1-optional-plugins`。

## 获取与启动

远程仓库为 https://github.com/AceUtr/Alternative-Frame 。成员已有克隆时，先保存自己的改动，再获取并切换共享分支：

```powershell
git fetch origin
git switch codex/v1.1-optional-plugins
cd alternative-frame/v1.1-experimental
python ui.py
```

首次克隆可以直接选定分支：

```powershell
git clone --branch codex/v1.1-optional-plugins https://github.com/AceUtr/Alternative-Frame.git
cd Alternative-Frame/alternative-frame/v1.1-experimental
python ui.py
```

需要 Python 3.10+ 和 tkinter；Windows 也可双击 `启动长程任务UI.bat`。测试需要另装 pytest。真实任务由成员在自己的 UI 中配置 API；仓库不附共享密钥。本版没有新增第三方运行依赖。

日常任务入口是 `ui.py`；`ui_v1_1.py` 是独立组件实验控制台。主界面选择 API 模式、标准多 Agent 或长程任务后，通过“选择插件…”勾选所需组合。使用独立空工作目录，确认合同后执行。适用范围、启用位置与恢复约束见 [OPTIONAL_PLUGINS.md](OPTIONAL_PLUGINS.md)。

## 本轮发布内容

- 源码基线提交 `aaeec11a1bc23bc0dda51a0b14832b3d0ac0d661`：BM25 运行记忆、依赖消息、SQLite 执行队列、用量交叉审计，以及主界面勾选接入、运行锁与恢复保护。
- 配套的插件测试与历史 API 基线导出脚本。
- `examples/noise_ablation_experiment.py`：固定工作负载的有界通信对照，包含清晰的估算口径和解释范围。
- 本轮修正：元数据测试明确按 UTF-8 读取 JSON，并使用中文运行目录，避免 Windows 本地编码导致测试失败。没有改动模型执行逻辑。
- 本轮复测结果、通信实验 JSON 与文件哈希清单，见 [证据目录](evidence/github-publish-20261111/)。

## 本轮验证与解释范围

在由 `aaeec11` 导出的独立源码副本中，加入本轮 UTF-8 测试修正与通信脚本后运行：

```powershell
python -m pytest -q --basetemp=<独立临时目录> --junitxml=<结果文件>
python examples/noise_ablation_experiment.py
```

全量测试：**218 passed，0 failed**。其中包含插件专项与 Tk 控件检查，不等同于完整人工桌面体验验收。没有使用本地已改写的任务需求文档替代提交中的验收基线。

通信实验：5 个 Agent，每组 5 次；送达消息均值 OFF=311、ON=5，两组均完成。报告中的 token 是字符粗估，**不是供应商 usage**；该实验不含真实 LLM 调用，不证明真实 API 的质量、耗时或费用提升。全部组合、仅 BM25 等同版本真实 API 对照仍待实施。

本轮没有发送真实 API 请求。历史 `c97d17f0cc0b` 的 25 项产物测试、18 个文件哈希复核与后续阶段上限停止应分别解释，不能把这些记录拼成最终完整长程成功。本轮没有重新验收这些历史产物。

初次复测曾因测试使用系统默认 GBK 读取包含中文路径的 UTF-8 文件而出现 217 passed、1 failed。修正并重新执行后得到上述 218 passed；初次失败和最终通过的原始输出均保留。

## 本地内容整理原则

本轮提交不纳入运行目录 `runs/`、本地原始 `reports/`、任务生成的 `src/scientific_calculator/`，这些路径由 `.gitignore` 排除；可共享验证记录放在 `docs/evidence/`，并保留 SHA-256。

既有 `v0.1` 的四项修改及其未跟踪辅助源码、v1.1 已改写的 `requirements.md` 和计算器文件已在发布者本地单独留档，保留原文件，不混入插件发布。`v1.0` 本地副本、测试缓存、历史运行、其他工作区和大型源码归档也不整包上传。此分支供成员获取插件增强版，不移动候选 tag，也不直接改写 `main`。

验证基线、证据类型、源码及结果哈希见 `evidence/github-publish-20261111/manifest.json`。获取后可用 `git rev-parse HEAD` 记录实际使用的发布提交；后续工作应从共享分支建立个人分支，保留任务和证据来源。
