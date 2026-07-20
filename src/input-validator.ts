import type { CreateAnalysisCommand, ValidationIssue } from "./models.ts";

export const LIMITS = {
  maxSources: 100,
  maxSourceLength: 20_000,
  maxTotalLength: 100_000,
} as const;

export class InvalidInputError extends Error {
  constructor(public readonly issues: ValidationIssue[]) {
    super("至少需要一条非空原始需求");
    this.name = "InvalidInputError";
  }
}

export function validateInput(command: CreateAnalysisCommand): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const sources = Array.isArray(command?.sources) ? command.sources : [];

  if (sources.length === 0) {
    issues.push(issue("SOURCES_REQUIRED", "sources", "至少需要一条非空原始需求"));
    return issues;
  }
  if (sources.length > LIMITS.maxSources) {
    issues.push(issue("TOO_MANY_SOURCES", "sources", `原始需求条目不能超过 ${LIMITS.maxSources} 条`));
  }

  const seen = new Set<string>();
  let totalLength = 0;
  sources.forEach((source, index) => {
    const path = `sources[${index}]`;
    const sourceId = typeof source?.sourceId === "string" ? source.sourceId.trim() : "";
    const content = typeof source?.content === "string" ? source.content : "";
    totalLength += content.length;

    if (!sourceId) issues.push(issue("SOURCE_ID_REQUIRED", `${path}.sourceId`, "sourceId 不能为空"));
    else if (seen.has(sourceId)) issues.push(issue("DUPLICATE_SOURCE_ID", `${path}.sourceId`, "sourceId 在请求内必须唯一"));
    else seen.add(sourceId);

    if (!content.trim()) issues.push(issue("SOURCE_CONTENT_REQUIRED", `${path}.content`, "原始需求内容不能为空"));
    if (content.length > LIMITS.maxSourceLength) {
      issues.push(issue("SOURCE_TOO_LONG", `${path}.content`, `单条原始需求不能超过 ${LIMITS.maxSourceLength} 个字符`));
    }
  });

  if (totalLength > LIMITS.maxTotalLength) {
    issues.push(issue("TOTAL_CONTENT_TOO_LONG", "sources", `原始需求总长度不能超过 ${LIMITS.maxTotalLength} 个字符`));
  }
  return issues;
}

function issue(code: string, path: string, message: string): ValidationIssue {
  return { code, path, severity: "ERROR", message };
}
