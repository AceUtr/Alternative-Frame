# Milestone 11: 队员贡献统一验收门禁

本里程碑新增配置驱动的 `validate_contribution.py`，为软件工程、科研、端边云和评测模块提供一致的合并前检查。

## 结构

```text
validate_contribution.py
validation/
  runner.py
  manifests/
reports/contribution-validation/
tests/test_contribution_validation.py
docs/contribution-validation.md
```

## 关键约束

- 外部命令使用参数数组和 `shell=False`。
- Adapter 必须通过现有 `HarnessPreflightChecker`。
- 测试和 smoke 有独立超时。
- 前置检查失败时不运行 smoke。
- 报告数据进行密钥和个人路径脱敏。
- 报告 JSON 不进入 Git。

当前四类贡献尚未全部完成，因此初次运行返回 `1` 是预期结果。随着队员交付文件、Adapter、测试和 Demo，各项检查会逐步转为 `passed`。
