import test from "node:test";
import assert from "node:assert/strict";
import { LIMITS, InvalidInputError, validateInput } from "../src/input-validator.ts";
import { createAnalysis } from "../src/service.ts";

const source = (content: string, sourceId = "SRC-001") => ({ sourceId, content });

test("FR-001 accepts a non-empty source", () => {
  assert.deepEqual(validateInput({ sources: [source("用户应能够下载报表。")] }), []);
});

test("FR-001 rejects empty and whitespace-only content without creating output", () => {
  for (const content of ["", "  \n\t"]) {
    assert.throws(() => createAnalysis({ sources: [source(content)] }), (error: unknown) => {
      assert.ok(error instanceof InvalidInputError);
      assert.ok(error.issues.some((issue) => issue.code === "SOURCE_CONTENT_REQUIRED"));
      return true;
    });
  }
});

test("validates source IDs, count and length boundaries", () => {
  assert.ok(validateInput({ sources: [source("x", ""), source("y", "A"), source("z", "A")] }).some((x) => x.code === "DUPLICATE_SOURCE_ID"));
  assert.equal(validateInput({ sources: [source("x".repeat(LIMITS.maxSourceLength))] }).length, 0);
  assert.ok(validateInput({ sources: [source("x".repeat(LIMITS.maxSourceLength + 1))] }).some((x) => x.code === "SOURCE_TOO_LONG"));
});
