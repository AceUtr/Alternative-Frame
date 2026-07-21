import type { ValidationIssue } from "./models.ts";

export type ErrorCode =
  | "MALFORMED_REQUEST"
  | "INPUT_INVALID"
  | "ANALYSIS_FAILED"
  | "RESULT_INCONSISTENT";

export interface ErrorResponse {
  error: {
    code: ErrorCode;
    message: string;
    issues: ValidationIssue[];
    clarificationHints: string[];
  };
}

export class ApplicationError extends Error {
  readonly code: ErrorCode;
  readonly issues: ValidationIssue[];
  readonly clarificationHints: string[];

  constructor(
    code: ErrorCode,
    message: string,
    issues: ValidationIssue[] = [],
    clarificationHints: string[] = [],
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "ApplicationError";
    this.code = code;
    this.issues = issues;
    this.clarificationHints = clarificationHints;
  }
}

export function toErrorResponse(error: unknown): ErrorResponse {
  if (error instanceof ApplicationError) {
    return {
      error: {
        code: error.code,
        message: error.message,
        issues: error.issues,
        clarificationHints: error.clarificationHints,
      },
    };
  }
  return {
    error: {
      code: "ANALYSIS_FAILED",
      message: "需求分析执行失败",
      issues: [],
      clarificationHints: [],
    },
  };
}
