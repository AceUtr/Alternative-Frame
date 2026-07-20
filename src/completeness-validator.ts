import type { AnalysisResult, ValidationIssue } from "./models.ts";

export function validateCompleteness(result: AnalysisResult): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (!result.objective?.trim()) add(issues, "OBJECTIVE_REQUIRED", "objective", "需求目标不能为空");

  const requirementIds = new Set<string>();
  result.requirements.forEach((requirement, index) => {
    const path = `requirements[${index}]`;
    if (!requirement.id) add(issues, "REQUIREMENT_ID_REQUIRED", `${path}.id`, "需求标识不能为空");
    else if (requirementIds.has(requirement.id)) add(issues, "DUPLICATE_REQUIREMENT_ID", `${path}.id`, "需求标识必须唯一");
    else requirementIds.add(requirement.id);
    if (!requirement.statement?.trim()) add(issues, "REQUIREMENT_STATEMENT_REQUIRED", `${path}.statement`, "需求陈述不能为空");
    if (!requirement.sourceReferences?.length) add(issues, "SOURCE_REFERENCE_REQUIRED", `${path}.sourceReferences`, "需求必须可追踪到原始输入");
  });

  const criterionIds = new Set<string>();
  result.acceptanceCriteria.forEach((criterion, index) => {
    const path = `acceptanceCriteria[${index}]`;
    if (criterionIds.has(criterion.id)) add(issues, "DUPLICATE_CRITERION_ID", `${path}.id`, "验收条件标识必须唯一");
    criterionIds.add(criterion.id);
    if (!requirementIds.has(criterion.requirementId)) add(issues, "UNKNOWN_REQUIREMENT", `${path}.requirementId`, "验收条件必须关联已存在的需求");
    for (const field of ["given", "when", "then"] as const) {
      if (!criterion[field]?.trim()) add(issues, "CRITERION_FIELD_REQUIRED", `${path}.${field}`, "验收条件必须包含 Given/When/Then");
    }
  });

  result.requirements.forEach((requirement, index) => {
    if (!result.acceptanceCriteria.some((criterion) => criterion.requirementId === requirement.id)) {
      add(issues, "ACCEPTANCE_CRITERION_REQUIRED", `requirements[${index}]`, "每个需求至少需要一条验收条件");
    }
  });

  result.clarifications.forEach((clarification, index) => {
    if (!clarification.impact?.trim()) add(issues, "CLARIFICATION_IMPACT_REQUIRED", `clarifications[${index}].impact`, "待澄清项必须说明影响");
  });
  return issues;
}

function add(issues: ValidationIssue[], code: string, path: string, message: string): void {
  issues.push({ code, path, severity: "ERROR", message });
}
