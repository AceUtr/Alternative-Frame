import assert from "node:assert/strict";
import { createAnalysis } from "./service.ts";
import { renderMarkdown } from "./result-renderer.ts";

const result = createAnalysis({
  sources: [{ sourceId: "SRC-001", content: "用户可以使用邮箱和密码登录。连续输入错误密码 5 次后锁定账户。" }],
}, "CHECK-001");
assert.equal(result.requirements.length, 2);
assert.ok(result.requirements.every((requirement) => result.acceptanceCriteria.some((item) => item.requirementId === requirement.id)));
assert.match(renderMarkdown(result), /无已知依赖/);
console.log("local check passed");
