import type { AnalysisResult } from "./models.ts";

export type OutputFormat = "json" | "markdown";

export function renderResult(result: AnalysisResult, format: OutputFormat): string {
  return format === "json" ? JSON.stringify(result, null, 2) : renderMarkdown(result);
}

export function renderMarkdown(result: AnalysisResult): string {
  const lines: string[] = [
    "# 需求分析结果",
    "",
    "## 需求目标",
    result.objective,
    "",
    "## 功能需求与验收条件",
  ];

  for (const requirement of result.requirements) {
    lines.push("", `### ${requirement.id}`, requirement.statement, "", "**验收条件**");
    const criteria = result.acceptanceCriteria.filter((item) => item.requirementId === requirement.id);
    for (const criterion of criteria) {
      lines.push(
        `- ${criterion.id} [${criterion.scenarioType}] Given ${criterion.given}; When ${criterion.when}; Then ${criterion.then}`,
      );
    }
  }

  lines.push("", "## 依赖与假设");
  if (result.dependencies.length === 0) lines.push("无已知依赖。");
  else for (const dependency of result.dependencies) lines.push(`- ${dependency.id}：${dependency.description}（${dependency.confirmationStatus}）`);

  lines.push("", "## 待澄清项");
  if (result.clarifications.length === 0) lines.push("无。");
  else for (const item of result.clarifications) lines.push(`- ${item.id}：${item.question} 影响：${item.impact}`);

  lines.push("", "## 校验结果");
  if (result.validationIssues.length === 0) lines.push("完整性校验通过。");
  else for (const issue of result.validationIssues) lines.push(`- [${issue.severity}] ${issue.code} ${issue.path}: ${issue.message}`);
  return `${lines.join("\n")}\n`;
}
