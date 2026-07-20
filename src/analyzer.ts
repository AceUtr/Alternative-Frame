import type {
  AcceptanceCriterion,
  AnalysisResult,
  Clarification,
  CreateAnalysisCommand,
  Dependency,
  RecognizedContext,
  RecognizedItem,
  Requirement,
  SourceInput,
  SourceReference,
} from "./models.ts";

const vagueTerms = ["适当", "尽快", "及时", "友好", "快速", "良好", "高效", "稳定", "必要时", "合理"];
const externalSystemPattern = /([\p{Script=Han}A-Za-z0-9_-]{2,20}(?:网关|服务|系统|平台|API|接口))/gu;
const actorPattern = /^([\p{Script=Han}A-Za-z0-9_-]{1,20}?(?:人员|用户|管理员|客户|客服|访客|注册用户))/u;

export function analyze(command: CreateAnalysisCommand, taskId = crypto.randomUUID()): AnalysisResult {
  const requirements: Requirement[] = [];
  const acceptanceCriteria: AcceptanceCriterion[] = [];
  const dependencies: Dependency[] = suppliedDependencies(command);
  const clarifications: Clarification[] = [];
  const recognizedContext = emptyContext();

  for (const source of command.sources) {
    recognizeSource(source, recognizedContext);
    for (const raw of splitStatements(source.content)) {
      extractDependencies(raw, source, dependencies, recognizedContext);
      const vague = vagueTerms.filter((term) => raw.includes(term));
      const actionable = removeVagueClause(raw, vague);
      if (!actionable) {
        addVagueClarification(vague, [], source, clarifications);
        continue;
      }

      const requirementId = `R${requirements.length + 1}`;
      const reference = [{ sourceId: source.sourceId, quote: raw.trim() }];
      const parts = deriveBehavior(actionable);
      const requirement: Requirement = {
        id: requirementId,
        name: deriveName(actionable),
        statement: normalizeStatement(actionable),
        trigger: parts.trigger,
        processing: parts.processing,
        expectedOutcome: parts.expectedOutcome,
        state: vague.length ? "NEEDS_CLARIFICATION" : "DEFINED",
        category: inferCategory(actionable),
        sourceReferences: reference,
        dependencyIds: [],
        clarificationIds: [],
      };
      requirements.push(requirement);
      acceptanceCriteria.push(...createCriteria(requirement, actionable));
      addVagueClarification(vague, [requirementId], source, clarifications);
    }
  }

  linkRelations(requirements, dependencies, clarifications);
  addMissingInformationQuestions(recognizedContext, requirements, clarifications);
  const dependencyReport = dependencies.length
    ? { status: "HAS_DEPENDENCIES" as const, displayText: `已识别 ${dependencies.length} 项依赖`, items: dependencies }
    : { status: "NONE_KNOWN" as const, displayText: "无已知依赖", items: [] };

  return {
    taskId,
    objective: buildObjective(command.sources),
    recognizedContext,
    requirements,
    acceptanceCriteria,
    dependencies,
    dependencyReport,
    clarifications,
    assumptions: [],
    validationIssues: [],
    generatedAt: new Date().toISOString(),
  };
}

function splitStatements(content: string): string[] {
  return content
    .split(/[。；;\n]+/u)
    .flatMap((part) => part.split(/，(?:并且|同时)|并且|同时|并(?=发送|导出|调用|返回|显示|提供)/u))
    .map((part) => part.trim())
    .filter(Boolean);
}

function removeVagueClause(raw: string, vague: string[]): string {
  if (!vague.length) return raw.trim();
  const clauses = raw.split(/[，,]/u).map((item) => item.trim()).filter(Boolean);
  const concrete = clauses.filter((clause) => !vague.some((term) => clause.includes(term)));
  return concrete.join("，");
}

function normalizeStatement(raw: string): string {
  let text = raw.trim().replace(/[。；;]+$/u, "");
  text = text.replace(/^(系统|用户)(可以|能够|需要|必须|应该|应当)/u, "$1应");
  if (!/应/u.test(text.slice(0, 15))) text = `系统应${text}`;
  return `${text}。`;
}

function deriveName(raw: string): string {
  const cleaned = raw.replace(/^(系统|用户|[\p{Script=Han}A-Za-z0-9_-]{1,20}(?:人员|用户|管理员|客户|客服|访客))(可以|能够|需要|必须|应该|应当|应)?/u, "");
  return (cleaned.match(/(?:查询|显示|提示|提交|调用|完成|返回|锁定|下载|导出|发送|生成|提供|识别|记录|校验)[^，,]{0,12}/u)?.[0] ?? cleaned).slice(0, 24) || "系统行为";
}

function deriveBehavior(raw: string): Pick<Requirement, "trigger" | "processing" | "expectedOutcome"> {
  const conditional = raw.match(/^(.+?)(?:后|时|情况下)[，,]?(.+)$/u);
  const trigger = conditional?.[1]?.trim() ?? `用户或外部事件触发“${deriveName(raw)}”`;
  const behavior = conditional?.[2]?.trim() ?? raw.trim();
  const processing = `系统执行“${behavior}”`;
  const resultMatch = behavior.match(/(?:显示|提示|返回|生成|锁定|完成|拒绝)(.+)?$/u);
  const expectedOutcome = resultMatch ? `可观察到“${resultMatch[0]}”` : `系统状态或输出可观察地体现“${behavior}”`;
  return { trigger, processing, expectedOutcome };
}

function inferCategory(statement: string): Requirement["category"] {
  if (/(性能|响应时间|可用性|安全|友好|快速|高效|稳定)/u.test(statement)) return "QUALITY";
  if (/(必须|限制|不得|不能超过|大于|小于)/u.test(statement)) return "CONSTRAINT";
  return "FUNCTIONAL";
}

function createCriteria(requirement: Requirement, raw: string): AcceptanceCriterion[] {
  const criteria: AcceptanceCriterion[] = [{
    id: `${requirement.id}-AC1`, requirementId: requirement.id, title: "正常场景", scenarioType: "HAPPY_PATH",
    given: requirement.trigger ?? "已满足原始需求明确声明的前置条件",
    when: requirement.processing ?? `触发“${requirement.name}”`,
    then: requirement.expectedOutcome ?? `系统输出可观察地体现“${requirement.name}”`,
  }];
  if (/(不存在|超时|错误|失败|不得|拒绝)/u.test(raw)) {
    criteria.push({
      id: `${requirement.id}-AC${criteria.length + 1}`, requirementId: requirement.id, title: "异常场景", scenarioType: "EXCEPTION",
      given: "原始需求声明的异常条件成立", when: requirement.processing ?? `触发“${requirement.name}”`,
      then: requirement.expectedOutcome ?? "系统产生原始需求声明的可观察异常结果",
    });
  }
  const range = raw.match(/大于\s*(\d+).*?(?:不超过|小于等于)\s*(\d+)/u);
  if (range) {
    criteria.push({ id: `${requirement.id}-AC${criteria.length + 1}`, requirementId: requirement.id, title: "下边界", scenarioType: "BOUNDARY", given: `输入值等于 ${range[1]}`, when: requirement.processing ?? "提交输入", then: "系统拒绝该输入且不执行后续业务处理" });
    criteria.push({ id: `${requirement.id}-AC${criteria.length + 1}`, requirementId: requirement.id, title: "上边界", scenarioType: "BOUNDARY", given: `输入值等于 ${range[2]}`, when: requirement.processing ?? "提交输入", then: "系统接受该边界值并继续原始需求声明的处理" });
  }
  return criteria;
}

function addVagueClarification(terms: string[], requirementIds: string[], source: SourceInput, clarifications: Clarification[]): void {
  if (!terms.length) return;
  clarifications.push({
    id: `Q${clarifications.length + 1}`, category: "NON_FUNCTIONAL",
    question: `请明确“${terms.join("、")}”的可量化判定标准、统计口径和适用条件。`,
    impact: "缺少量化标准会导致实现范围和验收结果无法一致判定。",
    relatedRequirementIds: requirementIds,
    sourceReferences: [{ sourceId: source.sourceId, quote: source.content }],
  });
}

function suppliedDependencies(command: CreateAnalysisCommand): Dependency[] {
  const supplied = command.dependencies ?? [];
  const items = Array.isArray(supplied)
    ? supplied
    : Object.entries(supplied).map(([name, description]) => ({ name, description }));
  return items.filter((item) => item?.name).map((item, index) => ({
    id: `D${index + 1}`, type: item.type ?? "EXTERNAL_SYSTEM", name: item.name,
    description: item.description ? `${item.name}：${item.description}` : item.name,
    confirmationStatus: "CONFIRMED", sourceReferences: [],
  }));
}

function extractDependencies(raw: string, source: SourceInput, dependencies: Dependency[], context: RecognizedContext): void {
  for (const match of raw.match(externalSystemPattern) ?? []) {
    if (dependencies.some((item) => item.name === match || item.description.includes(match))) continue;
    const reference = [{ sourceId: source.sourceId, quote: raw.trim() }];
    dependencies.push({ id: `D${dependencies.length + 1}`, type: /API|接口/u.test(match) ? "API" : "EXTERNAL_SYSTEM", name: match, description: `依赖外部${match}`, confirmationStatus: "CONFIRMED", sourceReferences: reference });
    pushUnique(context.externalDependencies, match, reference);
  }
}

function recognizeSource(source: SourceInput, context: RecognizedContext): void {
  for (const raw of splitStatements(source.content)) {
    const refs = [{ sourceId: source.sourceId, quote: raw }];
    const actor = raw.match(actorPattern)?.[1];
    if (actor) pushUnique(context.actors, actor, refs);
    if (/(目标|为了|以便)/u.test(raw)) pushUnique(context.businessGoals, raw, refs);
    if (/(可以|能够|应|提交|查询|下载|导出|发送|调用)/u.test(raw)) {
      pushUnique(context.scenarios, raw, refs);
      pushUnique(context.functionalScope, deriveName(raw), refs);
    }
    if (/(必须|不得|大于|小于|不超过|仅限)/u.test(raw)) pushUnique(context.businessRules, raw, refs);
    if (/(输入|提交|使用).*(金额|账户|订单号|邮箱|密码|参数|文件)/u.test(raw)) pushUnique(context.inputs, raw, refs);
    if (/(显示|返回|提示|输出|生成|下载)/u.test(raw)) pushUnique(context.outputs, raw, refs);
    if (/(不存在|超时|错误|失败|异常)/u.test(raw)) pushUnique(context.exceptionScenarios, raw, refs);
    if (/(响应时间|性能|安全|兼容|合规|不得|限制|不超过)/u.test(raw)) pushUnique(context.constraints, raw, refs);
  }
}

function addMissingInformationQuestions(context: RecognizedContext, requirements: Requirement[], clarifications: Clarification[]): void {
  const checks: Array<[RecognizedItem[], Clarification["category"], string, string]> = [
    [context.businessGoals, "BUSINESS_GOAL", "该需求要达成的业务目标是什么？", "缺少业务目标会影响范围优先级判断。"],
    [context.actors, "ACTOR", "目标用户或系统角色有哪些？", "缺少角色会影响权限、触发条件和验收前置条件。"],
    [context.scenarios, "SCENARIO", "主要使用场景及触发流程是什么？", "缺少场景会影响正常与异常流程覆盖。"],
  ];
  for (const [items, category, question, impact] of checks) {
    if (items.length || clarifications.some((item) => item.category === category)) continue;
    clarifications.push({ id: `Q${clarifications.length + 1}`, category, question, impact, relatedRequirementIds: requirements.map((item) => item.id), sourceReferences: [] });
  }
  if (!requirements.length) {
    const more: Array<[Clarification["category"], string]> = [
      ["SCOPE", "需要拆解的具体业务需求、功能范围及明确非目标是什么？"],
      ["BUSINESS_RULE", "需要遵循哪些业务规则？"],
      ["NON_FUNCTIONAL", "是否存在性能、安全、兼容性或合规要求？"],
      ["DEPENDENCY", "是否存在外部系统、接口、数据或前置功能依赖？"],
    ];
    for (const [category, question] of more) clarifications.push({ id: `Q${clarifications.length + 1}`, category, question, impact: "缺失信息阻碍形成明确、可实现、可测试的原子需求。", relatedRequirementIds: [], sourceReferences: [] });
  }
}

function linkRelations(requirements: Requirement[], dependencies: Dependency[], clarifications: Clarification[]): void {
  for (const requirement of requirements) {
    requirement.dependencyIds = dependencies.filter((dependency) => dependency.sourceReferences.some((ref) => requirement.sourceReferences.some((reqRef) => reqRef.sourceId === ref.sourceId && (!ref.quote || reqRef.quote?.includes(dependency.name ?? ""))))).map((item) => item.id);
    requirement.clarificationIds = clarifications.filter((item) => item.relatedRequirementIds.includes(requirement.id)).map((item) => item.id);
  }
}

function emptyContext(): RecognizedContext {
  return { businessGoals: [], actors: [], scenarios: [], functionalScope: [], businessRules: [], inputs: [], outputs: [], exceptionScenarios: [], constraints: [], externalDependencies: [] };
}

function pushUnique(items: RecognizedItem[], text: string, sourceReferences: SourceReference[]): void {
  if (!items.some((item) => item.text === text)) items.push({ text, sourceReferences });
}

function buildObjective(sources: SourceInput[]): string {
  const titles = sources.map((source) => source.title?.trim()).filter(Boolean);
  return titles.length ? `分析并结构化拆解：${titles.join("、")}` : "将原始业务需求拆解为可追踪、可测试的结构化需求。";
}
