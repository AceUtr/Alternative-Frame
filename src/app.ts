import { readFile } from "node:fs/promises";
import { createAnalysis } from "./service.ts";
import { ApplicationError, toErrorResponse } from "./errors.ts";
import { renderResult, type OutputFormat } from "./result-renderer.ts";
import type { CreateAnalysisCommand } from "./models.ts";

async function main(): Promise<void> {
  const file = process.argv[2];
  const format = (process.argv[3] ?? "json") as OutputFormat;
  if (!file) {
    console.error("用法: npm start -- <input.json> [json|markdown]");
    process.exitCode = 2;
    return;
  }
  if (format !== "json" && format !== "markdown") {
    throw new ApplicationError("MALFORMED_REQUEST", "输出格式必须是 json 或 markdown");
  }

  let command: CreateAnalysisCommand;
  try {
    command = JSON.parse(await readFile(file, "utf8")) as CreateAnalysisCommand;
  } catch (error) {
    if (error instanceof SyntaxError) throw new ApplicationError("MALFORMED_REQUEST", "输入文件不是有效 JSON", [], [], { cause: error });
    throw error;
  }
  const result = createAnalysis(command);
  process.stdout.write(renderResult(result, format));
}

main().catch((error: unknown) => {
  console.error(JSON.stringify(toErrorResponse(error), null, 2));
  process.exitCode = 1;
});
