import test from "node:test";
import assert from "node:assert/strict";
import { ApplicationError, toErrorResponse } from "../src/errors.ts";
import { InvalidInputError } from "../src/input-validator.ts";
import { createAnalysis } from "../src/service.ts";

test("empty input maps to a stable INPUT_INVALID contract with clarification guidance", () => {
  assert.throws(() => createAnalysis({ sources: [] }), (error: unknown) => {
    assert.ok(error instanceof InvalidInputError);
    const response = toErrorResponse(error);
    assert.equal(response.error.code, "INPUT_INVALID");
    assert.ok(response.error.issues.some((issue) => issue.code === "SOURCES_REQUIRED"));
    assert.ok(response.error.clarificationHints.some((hint) => hint.includes("业务目标")));
    return true;
  });
});

test("unexpected errors are sanitized", () => {
  const response = toErrorResponse(new Error("secret stack detail"));
  assert.deepEqual(response, {
    error: { code: "ANALYSIS_FAILED", message: "需求分析执行失败", issues: [], clarificationHints: [] },
  });
});

test("application errors preserve machine-readable codes", () => {
  const response = toErrorResponse(new ApplicationError("MALFORMED_REQUEST", "输入不是有效 JSON"));
  assert.equal(response.error.code, "MALFORMED_REQUEST");
});
