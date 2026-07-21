import { analyze } from "./analyzer.ts";
import { validateCompleteness } from "./completeness-validator.ts";
import { ApplicationError } from "./errors.ts";
import { InvalidInputError, validateInput } from "./input-validator.ts";
import type { AnalysisResult, CreateAnalysisCommand } from "./models.ts";

export class InvalidAnalysisResultError extends ApplicationError {
  readonly result: AnalysisResult;

  constructor(result: AnalysisResult) {
    super("RESULT_INCONSISTENT", "分析结果未通过完整性校验", result.validationIssues);
    this.name = "InvalidAnalysisResultError";
    this.result = result;
  }
}

/** Runs the deterministic first-version analysis pipeline and only returns a complete result. */
export function createAnalysis(command: CreateAnalysisCommand, taskId?: string): AnalysisResult {
  const inputIssues = validateInput(command);
  if (inputIssues.some((issue) => issue.severity === "ERROR")) {
    throw new InvalidInputError(inputIssues);
  }

  let result: AnalysisResult;
  try {
    result = analyze(command, taskId);
  } catch (error) {
    throw new ApplicationError("ANALYSIS_FAILED", "需求分析执行失败", [], [], { cause: error });
  }
  result.validationIssues = validateCompleteness(result);
  if (result.validationIssues.some((issue) => issue.severity === "ERROR")) {
    throw new InvalidAnalysisResultError(result);
  }
  return result;
}
