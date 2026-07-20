import test from "node:test";
import assert from "node:assert/strict";
import { createAnalysis } from "../src/service.ts";
import { renderMarkdown, renderResult } from "../src/result-renderer.ts";

test("FR-005 markdown contains all mandatory sections and empty-state labels", () => {
  const result = createAnalysis({ sources: [{ sourceId: "S1", content: "用户应能够下载报表。" }] }, "T1");
  const markdown = renderMarkdown(result);
  for (const heading of ["需求目标", "功能需求与验收条件", "依赖与假设", "待澄清项", "校验结果"]) assert.match(markdown, new RegExp(heading));
  assert.match(markdown, /无已知依赖/);
  assert.match(markdown, /完整性校验通过/);
});

test("JSON rendering preserves the domain result", () => {
  const result = createAnalysis({ sources: [{ sourceId: "S1", content: "用户应能够下载报表。" }] }, "T1");
  assert.deepEqual(JSON.parse(renderResult(result, "json")), result);
});
