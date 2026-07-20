import { analyze } from "./analyzer.ts";
import { validateCompleteness } from "./completeness-validator.ts";
import { InvalidInputError, validateInput } from "./input-validator.ts";
import type { AnalysisResult, CreateAnalysisCommand } from "./models.ts";

export class InvalidAnalysisResultError extends Error {
  constructor(public readonly result: AnalysisResult) {
    super("分析结果未通过完整性校验");
    this.name = "InvalidAnalysisResultError";
  }
}

/** Runs the deterministic first-version analysis pipeline. */
export function createAnalysis(command: CreateAnalysisCommand, taskId?: string): AnalysisResult {
  const inputIssues = validateInput(command);
  if (inputIssues.some((issue) => issue.severity === "ERROR")) {
    throw new InvalidInputError(inputIssues);
  }

  const result = analyze(command, taskId);
  result.validationIssues = validateCompleteness(result);
  if (result.validationIssues.some((issue) => issue.severity === "ERROR")) {
    throw new InvalidAnalysisResultError(result);
  }
  return result;
}
