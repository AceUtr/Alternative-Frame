import test from "node:test";
import assert from "node:assert/strict";
import { validateCompleteness } from "../src/completeness-validator.ts";
import type { AnalysisResult } from "../src/models.ts";

function validResult(): AnalysisResult {
  return {
    taskId: "T1",
    objective: "目标",
    recognizedContext: { businessGoals: [], actors: [], scenarios: [], functionalScope: [], businessRules: [], inputs: [], outputs: [], exceptionScenarios: [], constraints: [], externalDependencies: [] },
    requirements: [{ id: "FR-001", name: "行为", statement: "系统应执行行为。", trigger: "前置", processing: "触发", expectedOutcome: "结果", state: "DEFINED", category: "FUNCTIONAL", sourceReferences: [{ sourceId: "S1" }], dependencyIds: [], clarificationIds: [] }],
    acceptanceCriteria: [{ id: "AC-FR-001-01", requirementId: "FR-001", title: "正常", scenarioType: "HAPPY_PATH", given: "前置", when: "触发", then: "可观察结果" }],
    dependencies: [], dependencyReport: { status: "NONE_KNOWN", displayText: "无已知依赖", items: [] },
    clarifications: [], assumptions: [], validationIssues: [], generatedAt: new Date(0).toISOString(),
  };
}

test("complete result has no errors", () => assert.deepEqual(validateCompleteness(validResult()), []));

test("detects missing criteria and source traceability", () => {
  const result = validResult();
  result.requirements[0]!.sourceReferences = [];
  result.acceptanceCriteria = [];
  const codes = validateCompleteness(result).map((item) => item.code);
  assert.ok(codes.includes("SOURCE_REFERENCE_REQUIRED"));
  assert.ok(codes.includes("ACCEPTANCE_CRITERION_REQUIRED"));
});

test("detects unknown requirement and missing clarification impact", () => {
  const result = validResult();
  result.acceptanceCriteria[0]!.requirementId = "FR-404";
  result.clarifications.push({ id: "Q-001", question: "问题", impact: "", relatedRequirementIds: [], sourceReferences: [] });
  const codes = validateCompleteness(result).map((item) => item.code);
  assert.ok(codes.includes("UNKNOWN_REQUIREMENT"));
  assert.ok(codes.includes("CLARIFICATION_IMPACT_REQUIRED"));
});
