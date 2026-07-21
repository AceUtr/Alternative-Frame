# 核心业务实现说明

## 实现范围

- `src/models.ts`：定义输入、需求、验收条件、依赖、待澄清项、识别上下文和分析结果模型。
- `src/input-validator.ts`：校验来源存在性、唯一标识、内容及总量边界，并校验调用方依赖。
- `src/analyzer.ts`：执行语句拆分、需求规范化、验收条件生成、依赖识别、模糊信息隔离和关系关联。
- `src/completeness-validator.ts`：失败关闭地校验需求来源、唯一 ID、Given/When/Then 和引用完整性。
- `src/service.ts`：编排输入校验、分析和结果校验；不返回不完整结果。
- `src/errors.ts`：提供稳定错误码、统一错误响应和未知异常脱敏。
- `src/app.ts`：提供 JSON 文件输入的 CLI 适配器及 JSON/Markdown 输出；无效 JSON 映射为 `MALFORMED_REQUEST`。

## 错误处理

| 错误码 | 触发条件 |
|---|---|
| `MALFORMED_REQUEST` | JSON 或输出格式不合法 |
| `INPUT_INVALID` | 来源为空、字段或边界校验失败；响应包含补充信息提示 |
| `ANALYSIS_FAILED` | 核心分析过程异常或未知异常 |
| `RESULT_INCONSISTENT` | 生成结果未通过完整性校验 |

空输入不生成业务需求；通过 `issues` 明确指出缺少原始需求，并通过 `clarificationHints` 提示补充业务目标、角色、场景、范围、规则和非功能约束。

## 测试

自动化测试位于 `tests/*.test.ts`，覆盖输入边界、原子拆分、防臆造、验收条件、依赖、完整性校验、输出和错误契约。局部检查入口为 `npm run check`。

## 限制

当前实现是确定性规则分析器和 CLI 适配器，不是完整 HTTP 服务。自然语言规则只覆盖当前测试所需的通用表达，复杂语义、跨句指代和领域规则需要后续通过 `TextAnalysisEngine` 或领域适配器扩展。
