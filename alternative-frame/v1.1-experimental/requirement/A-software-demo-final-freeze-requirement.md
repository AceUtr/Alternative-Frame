# 软件工程 Demo 最终冻结任务书

## 目标

本任务完成后，软件工程 Demo 必须能够在干净环境中通过贡献门禁，并通过三个可现场演示的运行入口。只有全部硬性条件满足，队长才批准冻结。

当前基线：软件分支最新提交 `4f78297`。本任务只要求修复正式运行和验收闭环，不新增无关功能。

## P0 阻断项：补齐正式 CLI 入口

当前 `run_software_demo.py` 包含 Demo 逻辑，但缺少可执行的命令行入口。必须补齐：

1. `main()` 函数。
2. `argparse` 参数 `--fault-scenario`。
3. 支持且仅支持以下值：
   - `none`
   - `retry-once`
   - `local-recovery`
4. 文件末尾增加 `if __name__ == "__main__": main()`。
5. 直接运行脚本时必须真正执行任务，不能只返回退出码 0。

三个入口都必须在成功时输出或写入可机器检查的结果：

```text
Status: completed
Phase count: <positive integer>
Runtime root: <existing path>
```

失败时必须返回非零退出码，并输出明确错误原因。

## 三个场景的硬性语义

### 1. 正常场景

命令：

```powershell
python run_software_demo.py --fault-scenario none
```

要求：修复初始缺陷，精确执行合同要求的 pytest 命令，生成软件报告，最终状态为 `completed`。

### 2. 任务级重试

命令：

```powershell
python run_software_demo.py --fault-scenario retry-once
```

要求：

- 第一次实现故意失败或产生错误结果；
- 验收必须发现失败；
- 生成结构化 `retry_feedback`；
- 第二次执行读取反馈并修复；
- 最终 `Status: completed`；
- `events.jsonl` 或 `state.json` 能证明至少发生过一次重试，且前后尝试可区分。

### 3. 阶段内局部 DAG 恢复

命令：

```powershell
python run_software_demo.py --fault-scenario local-recovery
```

要求：

- 在下游测试或报告节点注入一次可恢复失败；
- 已成功的前置节点必须被冻结；
- 只重跑受影响节点及其必要后继；
- 最终 `Status: completed`；
- 运行状态或事件日志必须记录恢复周期、冻结节点和实际重跑节点。

## 证据产物

每次成功运行必须产生独立运行目录，至少包含：

```text
state.json
events.jsonl
workspace/artifacts/software_report.md
workspace/artifacts/code_diff.patch
workspace/artifacts/test_log.txt
```

`state.json` 必须包含最终状态、阶段、已完成任务、失败任务和验收结果。报告中的测试命令必须与合同中的精确命令一致：

```text
python -m pytest test_app.py -q -p no:cacheprovider
```

不得用手工填写的“测试通过”替代真实工具记录；必须有工具调用记录、退出码和当前运行产生的产物路径。

## 门禁必须真实验证 smoke

贡献门禁不能只检查脚本退出码为 0。请修改软件 manifest 或验证器，使 smoke 至少检查：

- 输出包含 `Status: completed`；
- 输出包含有效的 `Runtime root`；
- 该目录实际存在；
- `state.json` 的最终状态为 `completed`；
- 三个场景均生成对应的重试或局部恢复证据。

## 必须新增或保留的测试

至少覆盖：

1. CLI 默认/`none` 场景真实执行并完成。
2. 不支持的 `--fault-scenario` 返回非零退出码。
3. `retry-once` 产生一次结构化重试并最终完成。
4. `local-recovery` 不重复执行已冻结的成功节点。
5. 缺少工具证据时合同拒绝完成。
6. 过期报告或旧运行目录不能让当前运行虚假完成。

## 冻结前必须执行的命令

在干净工作树、Python 依赖已安装的环境中执行：

```powershell
python validate_contribution.py --domain software
python -m pytest tests/test_software_demo.py -q -p no:cacheprovider
python run_software_demo.py --fault-scenario none
python run_software_demo.py --fault-scenario retry-once
python run_software_demo.py --fault-scenario local-recovery
git diff --check
git status --short --branch
```

若 Windows 默认 pytest 临时目录权限异常，可使用新的可写目录作为 `--basetemp`；这属于环境问题，不能修改测试结果或跳过测试。

## 冻结标准

以下条件必须全部满足：

- 贡献门禁 `status=passed`；
- 软件专项测试全部通过；
- 三个 CLI 场景真实运行并均为 `completed`；
- 重试和局部恢复均有事件/状态证据；
- smoke 检查产物而非只检查退出码；
- `git diff --check` 通过；
- 无敏感信息、无临时运行产物、无 API Key；
- 提交说明列出命令、测试结果、运行目录和已知限制；
- 不修改 core 冻结接口、UI 公共契约或其他领域 Demo。

完成后请提交以下信息给队长：

```text
分支与提交：
门禁结果：
专项测试结果：
none 运行目录与状态：
retry-once 重试证据：
local-recovery 恢复证据：
git diff --check：
已知限制：
```

队长只有在上述信息可复核、三条命令可独立重跑后，才会将软件 Demo 标记为冻结。
