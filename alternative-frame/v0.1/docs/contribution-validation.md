# 队员贡献统一验收

## 用途

`validate_contribution.py` 是队员分支合并前的统一门禁。它检查文件结构、Python 导入、冻结接口、DomainAdapter、Harness Preflight、敏感信息、单元测试和 smoke Demo，并输出 JSON 报告。

验收失败不等于脚本故障。退出码定义：

```text
0：贡献通过全部启用的检查
1：贡献存在未通过项，禁止合并
2：验收器自身配置或执行异常
```

## 队长使用方法

在 `alternative-frame/v0.1` 中运行：

```powershell
python validate_contribution.py --domain software
python validate_contribution.py --domain research
python validate_contribution.py --runtime edge-cloud
python validate_contribution.py --module evaluation
```

默认执行完整验收，包括测试和 smoke Demo。第一次审查队员早期提交时，可以先跳过 smoke：

```powershell
python validate_contribution.py --domain research --skip-smoke
```

每条外部命令默认最多执行 180 秒，可以调整：

```powershell
python validate_contribution.py --domain software --timeout 300
```

## 报告位置

报告默认写入：

```text
reports/contribution-validation/<target>-<timestamp>.json
reports/contribution-validation/<target>-latest.json
```

报告目录中的 JSON 被 Git 忽略，不会污染提交。临时诊断时可禁用报告：

```powershell
python validate_contribution.py --module evaluation --skip-smoke --no-report
```

报告不会保存 API Key；疑似凭据和个人用户目录会被脱敏。

## 验收阶段

1. `structure`：需求书规定的入口、测试、文档和 fixture 是否存在。
2. `import`：贡献模块能否正常导入，语法和依赖是否完整。
3. `interface`：冻结的类和符号是否存在。
4. `preflight`：领域 Adapter 能否注册 Agent/工具、生成合同与 DAG 并通过启动预检。
5. `security`：扫描疑似 API Key、Bearer Token、硬编码 Secret 和个人绝对路径。
6. `tests`：运行贡献自己的单元测试。
7. `smoke`：前置项全部通过后才运行真实本地最小 Demo。

任何一个必需检查失败，最终状态都是 `failed`。如果结构或接口尚未完成，测试和 smoke 会显示 `skipped`，避免不完整代码继续修改工作区。

## 四类机器清单

清单位于 `validation/manifests/`：

```text
software.json
research.json
edge-cloud.json
evaluation.json
```

队员新增必要文件或合理调整入口时，应修改对应清单并在 PR 中解释原因。不得为了让检查通过而删除关键验收项。

## 推荐审查流程

```text
队员提交 PR
→ 队长切换到队员分支
→ 运行 --skip-smoke
→ 修复结构、接口、预检和安全问题
→ 运行完整验收
→ 查看 latest.json
→ 人工查看 Demo 产物与界面
→ 合并
```

机器验收通过是合并必要条件，不替代队长对设计、比赛价值和真实产物的人工审查。
