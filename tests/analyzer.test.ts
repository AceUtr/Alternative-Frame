import test from "node:test";
import assert from "node:assert/strict";
import { createAnalysis } from "../src/service.ts";

function run(content: string) {
  return createAnalysis({ sources: [{ sourceId: "SRC-001", content }] }, "TASK-001");
}

test("FR-002 splits compound input and assigns unique traceable IDs", () => {
  const result = run("用户可以使用邮箱和密码登录。连续输入错误密码 5 次后锁定账户。");
  assert.equal(result.requirements.length, 2);
  assert.equal(new Set(result.requirements.map((item) => item.id)).size, 2);
  assert.ok(result.requirements.every((item) => item.statement.includes("应") && item.sourceReferences[0]?.sourceId === "SRC-001"));
});

test("FR-002 preserves vague language as a clarification instead of inventing metrics", () => {
  const result = run("系统应尽量快速地生成报表，并提供友好的错误提示。");
  assert.ok(result.clarifications.length >= 1);
  assert.ok(result.clarifications.every((item) => item.impact.trim().length > 0));
  const allText = JSON.stringify(result);
  assert.doesNotMatch(allText, /\b\d+\s*(毫秒|秒|分钟)\b/u);
});

test("FR-003 creates at least one complete, traceable criterion per requirement", () => {
  const result = run("用户应能够下载报表。");
  for (const requirement of result.requirements) {
    const criteria = result.acceptanceCriteria.filter((item) => item.requirementId === requirement.id);
    assert.ok(criteria.length >= 1);
    assert.ok(criteria.every((item) => item.given && item.when && item.then));
  }
});

test("FR-004 extracts explicit external dependencies", () => {
  const result = run("系统应调用支付网关完成付款；支付网关地址由部署环境提供。");
  assert.ok(result.dependencies.some((item) => item.description.includes("支付网关")));
});
