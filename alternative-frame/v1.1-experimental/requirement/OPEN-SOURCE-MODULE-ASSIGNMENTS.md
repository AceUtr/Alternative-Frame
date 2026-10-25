# 开源项目模块交接总表

## 直接分配

| 成员板块 | 需要交接的项目 | 交接文件 |
|---|---|---|
| 科研 Demo 成员 | `GenExp`、`robin` | `research-genexp-robin-handoff.md` |
| 评测 / D 成员 | `science-sandbox` | `evaluation-science-sandbox-handoff.md` |
| 软件 Demo 成员 | 本轮无直接移植项目；提供评测消费接口 | `integration-coordination-note.md` |
| 端边云成员 | 本轮无直接移植项目；提供 runtime view 和运行证据 | `integration-coordination-note.md` |

## 不在本轮直接移植的项目

`AutoResearchClaw`、`AutoScientists`、`EvoScientist`、`InternAgent` 的通用能力已经进入 `core/experimental/` 原型，分别对应 Adapter/成本治理、队列租约、运行治理和混合记忆。科研成员和评测成员不得重复实现这些核心模块；需要使用时通过现有接口接入。

## 共同交接规则

1. 从队长指定的 v1.1-experimental 基线创建独立分支并记录 commit。
2. 一个板块一个分支，一个功能一个聚焦 commit。
3. 先跑本板块专项测试和门禁，再申请集成。
4. 提交代码、依赖、许可证、运行命令、测试结果、产物路径和已知限制。
5. 不提交 API Key、运行缓存、临时目录、`__pycache__` 或未经授权的数据/模型权重。
6. 不直接修改 v1.0；公共接口改动必须先提交变更说明和兼容性测试。
