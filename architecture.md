# 需求分析系统架构设计

## 1. 设计范围与约束

本文基于 `requirements.md` 中 FR-001～FR-006，设计一个将原始业务需求转换为“原子需求、验收条件、依赖和待澄清项”的最小可实现系统。

当前未提供具体业务领域，因此本设计仅定义通用分析能力，不引入登录、支付、审批等业务模块或规则。

### 1.1 设计目标

- 接收非空需求文本并返回结构化分析结果；
- 对空输入返回明确、可机器识别的校验错误及待澄清方向；
- 保证需求、验收条件和追踪关系的完整性；
- 将无法由输入证实的信息隔离为待澄清项；
- 支持同步实现，后续可在不改变核心模型的前提下扩展异步处理。

### 1.2 非目标

- 不定义具体业务领域模型；
- 不自动判定未经输入确认的业务事实；
- 不规定自然语言分析必须使用规则引擎或大模型；
- 不定义用户、租户、计费和持久化历史等未提出能力。

## 2. 总体架构

采用单体分层架构，优先保证简单可实现。首版可部署为一个无状态 HTTP 服务；分析结果直接响应调用方，不要求数据库。

```text
调用方
  |
  | HTTP/JSON
  v
Analysis API
  |
  v
Analysis Application Service
  |---- Input Validator
  |---- Requirement Decomposer
  |---- Acceptance Criteria Generator
  |---- Dependency Extractor
  |---- Clarification Collector
  |---- Result Validator / Traceability Builder
  v
Structured AnalysisResult
```

### 2.1 分层职责

| 层 | 职责 | 不负责 |
|---|---|---|
| API 层 | 协议转换、请求校验、HTTP 状态码、错误映射 | 需求拆解规则 |
| 应用层 | 编排分析步骤、组装结果 | 具体 HTTP 细节 |
| 领域层 | 原子需求、验收条件、依赖、待澄清项的生成与一致性校验 | 存储与网络 |
| 基础设施层 | 可插拔文本分析器、日志与可选持久化适配器 | 改变领域模型语义 |

## 3. 模块设计

### 3.1 Analysis API

**职责**

- 接收 `AnalyzeRequirementsRequest`；
- 执行协议级校验（JSON 格式、字段类型、请求大小上限由部署配置决定）；
- 调用 `AnalysisService.analyze`；
- 将领域错误映射为统一错误响应。

**接口**

```text
POST /v1/requirement-analyses
Content-Type: application/json
```

首版为同步接口。若分析耗时以后无法满足部署环境超时限制，可新增异步资源接口，而不修改本接口的数据模型。

### 3.2 Input Validator

**职责**

- 对 `sourceText` 去除首尾空白后判空；
- 校验调用方提供依赖的必需字段与枚举值；
- 只报告输入问题，不补造缺失业务信息。

**领域接口**

```ts
interface InputValidator {
  validate(request: AnalyzeRequirementsRequest): ValidationIssue[];
}
```

### 3.3 Requirement Decomposer

**职责**

- 从输入中提取单一职责、可独立验证的候选需求；
- 为需求分配本次结果内唯一且稳定的顺序标识 `FR-001`、`FR-002`……；
- 保留来源引用；无法追踪到输入的内容不得成为确认需求。

**领域接口**

```ts
interface RequirementDecomposer {
  decompose(context: AnalysisContext): Requirement[];
}
```

`sourceRefs` 使用输入文本的字符区间，便于校验事实来源；字符下标采用 Unicode code point、左闭右开区间，具体实现必须全局一致。

### 3.4 Acceptance Criteria Generator

**职责**

- 为每个可实施需求生成至少一项验收条件；
- 输出前置条件、触发动作和可观察结果；
- 信息不足以生成异常或边界场景时，不设定虚构阈值，而是交给待澄清模块。

**领域接口**

```ts
interface AcceptanceCriteriaGenerator {
  generate(requirement: Requirement, context: AnalysisContext): AcceptanceCriterion[];
}
```

### 3.5 Dependency Extractor

**职责**

- 合并调用方显式依赖与原文中可追踪的依赖；
- 依赖细节不足时标记 `PENDING_CONFIRMATION`；
- 没有已知依赖时返回空列表，并由结果摘要表达 `NO_KNOWN_DEPENDENCIES`。

**领域接口**

```ts
interface DependencyExtractor {
  extract(context: AnalysisContext): Dependency[];
}
```

### 3.6 Clarification Collector

**职责**

- 收集缺失、模糊、冲突以及会影响实现或验收的问题；
- 合并语义重复的问题；
- 生成本次结果内唯一标识 `Q-001`、`Q-002`……；
- 空业务输入时至少覆盖业务目标、角色与场景、功能范围、业务规则、非功能约束。

**领域接口**

```ts
interface ClarificationCollector {
  collect(context: AnalysisContext, draft: AnalysisDraft): Clarification[];
}
```

### 3.7 Result Validator / Traceability Builder

**职责**

- 验证标识唯一性和引用完整性；
- 验证每项可实施需求至少关联一个验收条件；
- 验证验收条件的 Given/When/Then 等价字段非空；
- 构建需求到验收条件的追踪项；
- 对内部生成的不一致结果失败关闭，不返回表面成功。

**领域接口**

```ts
interface ResultValidator {
  validate(result: AnalysisResult): ValidationIssue[];
}

interface TraceabilityBuilder {
  build(requirements: Requirement[], criteria: AcceptanceCriterion[]): TraceLink[];
}
```

### 3.8 Analysis Application Service

**职责**：按固定顺序编排模块，并形成事务边界。无数据库时，事务边界表示“只返回整体有效结果，不返回未经标记的部分成功结果”。

```ts
interface AnalysisService {
  analyze(request: AnalyzeRequirementsRequest): AnalysisResult;
}
```

推荐流程：

1. 规范化并校验输入；
2. 若 `sourceText` 为空，返回 `INPUT_INVALID`，同时在错误详情中给出补充原始需求的建议，不执行具体业务拆解；
3. 建立只读 `AnalysisContext`；
4. 拆解原子需求；
5. 为需求生成验收条件；
6. 提取依赖；
7. 收集待澄清项；
8. 构建追踪关系并执行结果一致性校验；
9. 返回完整 `AnalysisResult`。内部一致性校验失败时返回内部错误并记录诊断信息。

## 4. 外部接口

### 4.1 分析请求

```json
{
  "sourceText": "系统应……",
  "providedDependencies": [
    {
      "name": "外部系统名称",
      "type": "EXTERNAL_SYSTEM",
      "description": "调用方已确认的依赖说明"
    }
  ]
}
```

字段定义：

| 字段 | 类型 | 必需 | 规则 |
|---|---|---:|---|
| `sourceText` | string | 是 | 去除首尾空白后至少 1 个字符 |
| `providedDependencies` | array | 否 | 缺省为空数组 |
| `providedDependencies[].name` | string | 是 | 非空 |
| `providedDependencies[].type` | DependencyType | 是 | 必须为已定义枚举 |
| `providedDependencies[].description` | string | 是 | 非空，仅表达调用方已确认信息 |

### 4.2 成功响应

HTTP `200 OK`

```json
{
  "analysisId": "0195f4c0-7b4f-7000-8000-000000000001",
  "status": "COMPLETED",
  "requirements": [
    {
      "id": "FR-001",
      "statement": "系统应……",
      "implementability": "IMPLEMENTABLE",
      "sourceRefs": [{"start": 0, "end": 5}]
    }
  ],
  "acceptanceCriteria": [
    {
      "id": "AC-FR001-01",
      "requirementId": "FR-001",
      "given": ["已满足前置条件"],
      "when": "发生明确动作",
      "then": ["产生可观察结果"],
      "scenarioType": "HAPPY_PATH"
    }
  ],
  "dependencies": [],
  "dependencyState": "NO_KNOWN_DEPENDENCIES",
  "clarifications": [],
  "traceability": [
    {"requirementId": "FR-001", "acceptanceCriterionIds": ["AC-FR001-01"]}
  ]
}
```

### 4.3 错误响应

HTTP `400 Bad Request`：JSON 或字段类型不合法。  
HTTP `422 Unprocessable Entity`：请求结构正确，但 `sourceText` 为空或依赖字段违反领域校验。  
HTTP `500 Internal Server Error`：分析器异常或生成结果未通过内部一致性校验。

```json
{
  "error": {
    "code": "INPUT_INVALID",
    "message": "缺少原始业务需求",
    "issues": [
      {
        "path": "sourceText",
        "code": "REQUIRED",
        "message": "sourceText 去除首尾空白后不能为空"
      }
    ],
    "clarificationHints": [
      "请提供业务目标、目标角色、使用场景、功能范围、业务规则及非功能约束"
    ]
  }
}
```

错误代码：

| code | 含义 |
|---|---|
| `MALFORMED_REQUEST` | JSON 或字段类型错误 |
| `INPUT_INVALID` | 输入不满足领域前置条件 |
| `ANALYSIS_FAILED` | 分析器执行失败 |
| `RESULT_INCONSISTENT` | 生成结果未通过一致性校验 |

## 5. 数据模型

以下 TypeScript 仅作为明确、语言无关的数据契约；实现可使用其他语言并保持等价约束。

```ts
type DependencyType =
  | "EXTERNAL_SYSTEM"
  | "INTERFACE"
  | "DATA"
  | "PERMISSION"
  | "INFRASTRUCTURE"
  | "PREREQUISITE_FEATURE";

type DependencyStatus = "CONFIRMED" | "PENDING_CONFIRMATION";
type DependencyState = "HAS_DEPENDENCIES" | "NO_KNOWN_DEPENDENCIES";
type Implementability = "IMPLEMENTABLE" | "BLOCKED_BY_CLARIFICATION";
type ScenarioType = "HAPPY_PATH" | "ERROR_PATH" | "BOUNDARY";

interface AnalyzeRequirementsRequest {
  sourceText: string;
  providedDependencies?: ProvidedDependency[];
}

interface ProvidedDependency {
  name: string;
  type: DependencyType;
  description: string;
}

interface SourceRef {
  start: number; // inclusive
  end: number;   // exclusive; end > start
}

interface Requirement {
  id: string; // ^FR-[0-9]{3,}$
  statement: string;
  implementability: Implementability;
  sourceRefs: SourceRef[]; // 至少一个；仅任务级空输入错误场景除外且不生成 Requirement
}

interface AcceptanceCriterion {
  id: string; // ^AC-FR[0-9]{3,}-[0-9]{2,}$
  requirementId: string;
  given: string[]; // 至少一项
  when: string;
  then: string[];  // 至少一项且结果可观察
  scenarioType: ScenarioType;
}

interface Dependency {
  id: string; // ^DEP-[0-9]{3,}$
  name: string;
  type: DependencyType;
  description: string;
  status: DependencyStatus;
  source: "CALLER_PROVIDED" | "SOURCE_TEXT";
  sourceRefs: SourceRef[]; // source 为 SOURCE_TEXT 时至少一项
}

interface Clarification {
  id: string; // ^Q-[0-9]{3,}$
  question: string;
  impact: string;
  relatedRequirementIds: string[];
  sourceRefs: SourceRef[];
}

interface TraceLink {
  requirementId: string;
  acceptanceCriterionIds: string[];
}

interface AnalysisResult {
  analysisId: string; // UUID
  status: "COMPLETED";
  requirements: Requirement[];
  acceptanceCriteria: AcceptanceCriterion[];
  dependencies: Dependency[];
  dependencyState: DependencyState;
  clarifications: Clarification[];
  traceability: TraceLink[];
}

interface ValidationIssue {
  path: string;
  code: string;
  message: string;
}
```

### 5.1 模型不变量

1. 所有集合内 `id` 唯一；
2. `AcceptanceCriterion.requirementId` 必须引用现有需求；
3. 每个 `IMPLEMENTABLE` 需求至少有一项验收条件；
4. 每项验收条件只归属一个需求；
5. 每个需求恰有一个 `TraceLink`，且其中验收条件集合与实际归属一致；
6. `dependencies` 为空时 `dependencyState` 必须为 `NO_KNOWN_DEPENDENCIES`，否则为 `HAS_DEPENDENCIES`；
7. `PENDING_CONFIRMATION` 依赖必须对应至少一个说明其影响的待澄清项；
8. 正式需求陈述中的确定事实必须由 `sourceRefs` 指向输入来源；
9. `BLOCKED_BY_CLARIFICATION` 需求可以没有验收条件，但必须关联至少一个待澄清项；
10. 系统不得以默认值补充业务阈值、角色、权限或异常规则。

## 6. 核心处理策略

### 6.1 文本分析器抽象

为避免架构绑定具体实现，定义统一端口：

```ts
interface TextAnalysisEngine {
  extractRequirements(sourceText: string): RequirementCandidate[];
  generateCriteria(requirement: Requirement, sourceText: string): CriterionCandidate[];
  extractDependencies(sourceText: string): DependencyCandidate[];
  identifyGaps(sourceText: string, draft: AnalysisDraft): GapCandidate[];
}
```

可选实现：

- `RuleBasedTextAnalysisEngine`：适合格式固定、规则明确的输入；
- `ModelBackedTextAnalysisEngine`：适合自由文本，但其输出必须经过 schema 校验、来源校验和结果一致性校验。

应用服务只依赖接口，不直接依赖具体分析技术。

### 6.2 标识生成

在单次分析内按输出顺序生成：

- 需求：`FR-001` 起；
- 验收条件：`AC-{去掉 FR 中连字符后的需求号}-01`，例如 `AC-FR001-01`；
- 依赖：`DEP-001` 起；
- 待澄清项：`Q-001` 起。

标识只保证单次 `analysisId` 范围内唯一。若未来支持分析版本比较，应另行增加稳定实体 ID 和版本号，不复用当前顺序 ID 承担跨版本身份。

### 6.3 防臆造控制

- 每项正式需求必须具有非空 `sourceRefs`；
- 分析引擎输出只作为候选，必须经过结构与来源校验；
- 无来源、冲突或不确定的候选转为 `Clarification`，不得静默进入正式需求；
- 日志记录分析器版本和失败原因，但不得把未确认候选作为成功结果返回。

## 7. 关键时序

```text
Client -> API: POST request
API -> InputValidator: validate(request)
alt 输入无效
  API --> Client: 400/422 ErrorResponse
else 输入有效
  API -> AnalysisService: analyze(request)
  AnalysisService -> RequirementDecomposer: decompose(context)
  AnalysisService -> AcceptanceCriteriaGenerator: generate(each requirement)
  AnalysisService -> DependencyExtractor: extract(context)
  AnalysisService -> ClarificationCollector: collect(context, draft)
  AnalysisService -> TraceabilityBuilder: build(...)
  AnalysisService -> ResultValidator: validate(result)
  alt 结果不一致
    AnalysisService --> API: RESULT_INCONSISTENT
    API --> Client: 500 ErrorResponse
  else 结果有效
    AnalysisService --> API: AnalysisResult
    API --> Client: 200 AnalysisResult
  end
end
```

## 8. 部署、存储与可观测性

### 8.1 部署

- 首版：单进程、无状态 HTTP 服务；
- 可水平扩展，实例间不共享会话；
- 若采用外部模型或规则服务，通过基础设施适配器调用，并设置超时与有限重试；对非幂等外部调用不自动重试。

### 8.2 存储

首版不要求持久化。调用方负责保存响应。若后续要求审计或历史查询，可新增 `AnalysisRepository`：

```ts
interface AnalysisRepository {
  save(result: AnalysisResult): void;
  findById(analysisId: string): AnalysisResult | null;
}
```

仓储是可选适配器，不得成为核心分析流程的隐式依赖。

### 8.3 可观测性

最低记录：

- `analysisId`、请求追踪 ID、处理耗时、结果计数、错误代码、分析器版本；
- 默认不记录完整 `sourceText`，避免业务文本或敏感信息进入日志；
- 指标：请求数、成功率、输入错误率、内部一致性失败率、处理时延；
- 不声明具体 SLA 或阈值，等待非功能要求确认。

## 9. 安全与健壮性基线

- 对请求体大小设置可配置上限；具体值待非功能要求确认；
- 将输入作为数据处理，禁止其直接控制系统配置、工具调用或代码执行；
- 输出采用严格 schema 校验并进行 JSON 转义；
- 外部分析器凭据通过运行环境密钥注入，不写入源码或日志；
- 错误响应不暴露堆栈、凭据或内部模型原始响应；
- 身份认证、授权、数据保留期限因需求未提供，标记为待确认，不在本设计中假设。

## 10. 需求追踪

| 需求 | 架构实现点 |
|---|---|
| FR-001 | Analysis API、Input Validator、422 错误契约 |
| FR-002 | Requirement Decomposer、来源引用、标识生成、模型不变量 |
| FR-003 | Acceptance Criteria Generator、Given/When/Then 模型、Result Validator |
| FR-004 | Dependency Extractor、Dependency/DependencyState 模型 |
| FR-005 | Clarification Collector、Clarification 模型、防臆造控制 |
| FR-006 | AnalysisResult、Traceability Builder、结果一致性校验 |

## 11. 实施切分

1. 定义请求、响应、错误及领域模型；
2. 实现 Input Validator 与 Result Validator；
3. 实现 AnalysisService 编排和内存标识生成器；
4. 实现一个 `TextAnalysisEngine` 适配器；
5. 实现各领域模块，将候选输出转换为受约束模型；
6. 暴露 `POST /v1/requirement-analyses`；
7. 增加契约测试、模块单元测试和端到端测试。

最低测试集：

- 空、缺失和仅空白 `sourceText` 返回 422，且不生成业务需求；
- 有效输入返回完整必需字段；
- 多行为输入拆为具有唯一 ID 的多个需求；
- 每个可实施需求至少关联一项验收条件；
- 悬空引用、重复 ID、空 Given/When/Then 被结果校验器拒绝；
- 无依赖时状态正确，有待确认依赖时产生待澄清项；
- 无来源候选不能成为正式需求；
- 追踪矩阵与需求、验收条件实际关系一致。

## 12. 待确认与风险

| 项目 | 当前处理 | 风险 |
|---|---|---|
| 具体业务领域 | 不作假设 | 无法定义领域专用模块、术语和规则 |
| 分析引擎选型 | 通过 `TextAnalysisEngine` 隔离 | 不同引擎的准确性、成本和延迟未知 |
| 性能/SLA | 不设虚构阈值 | 无法确定同步接口是否长期适用 |
| 认证与授权 | 未设计具体机制 | 对外开放前必须补充访问控制要求 |
| 数据敏感级别与保留 | 默认日志不记录原文、首版不持久化 | 无法确认合规措施是否充分 |
| 字符区间规范 | 规定 Unicode code point | 各语言实现若使用 UTF-16 下标需显式转换 |

## 13. 架构验收

- [x] 已定义总体架构和模块边界；
- [x] 已为核心模块定义显式接口；
- [x] 已定义 HTTP 请求、成功响应和错误响应；
- [x] 已定义数据模型、枚举、引用及一致性约束；
- [x] 已追踪 FR-001～FR-006；
- [x] 已记录未知项，未虚构具体业务规则或非功能阈值。

**交付状态：`architecture_written = 通过`。**
