import { readFile } from "node:fs/promises";
import { createAnalysis } from "./service.ts";
import { InvalidInputError } from "./input-validator.ts";
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
  if (format !== "json" && format !== "markdown") throw new Error("输出格式必须是 json 或 markdown");

  const command = JSON.parse(await readFile(file, "utf8")) as CreateAnalysisCommand;
  const result = createAnalysis(command);
  process.stdout.write(renderResult(result, format));
}

main().catch((error: unknown) => {
  if (error instanceof InvalidInputError) {
    console.error(JSON.stringify({ code: "INVALID_INPUT", message: error.message, issues: error.issues }, null, 2));
    process.exitCode = 1;
    return;
  }
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
});
