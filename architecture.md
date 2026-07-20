# 需求分析系统架构设计

## 1. 设计范围

本文基于 `requirements.md` 中 FR-001 至 FR-006，设计一个将原始业务需求转换为原子需求、验收条件、依赖和待澄清项的分析服务。

当前没有具体业务域、目标角色、业务规则或非功能指标，因此本设计只定义任务级模块、接口和数据模型，不假定登录、数据库、消息队列、第三方 AI 服务或其他外部系统必然存在。

## 2. 架构原则

1. **事实可追踪**：正式需求中的确定性事实必须引用输入来源。
2. **待确认内容隔离**：不确定信息进入待澄清项，不进入已确认需求。
3. **确定性校验**：结构完整性、标识唯一性和引用完整性由规则校验器完成。
4. **分析器可替换**：需求理解能力通过接口注入，可采用规则、人工流程或模型实现。
5. **无状态优先**：单次分析通过请求与响应完成；持久化仅在后续确认需要历史记录时增加。

## 3. 系统上下文

```text
调用方
  |
  | AnalyzeRequest / AnalyzeResponse
  v
需求分析服务
  |-- 输入规范化
  |-- 需求拆解
  |-- 验收条件生成
  |-- 依赖识别
  |-- 待澄清项管理
  `-- 结果校验与组装

可选适配器（未确认依赖）
  |-- 分析引擎实现：规则 / 人工 / 外部模型
  `-- 结果仓储实现：内存 / 文件 / 数据库
```

服务核心不直接依赖特定传输协议、模型供应商或存储产品。

## 4. 模块设计

| 模块 | 职责 | 输入 | 输出 | 追踪需求 |
|---|---|---|---|---|
| `AnalysisApplicationService` | 编排完整分析流程，统一处理失败 | `AnalyzeCommand` | `AnalysisResult` | FR-001, FR-006 |
| `InputNormalizer` | 去除首尾空白、规范来源，判定空输入 | 原始文本、依赖 | `NormalizedInput` | FR-001 |
| `RequirementDecomposer` | 拆分单一职责需求，保留来源引用 | `NormalizedInput` | `Requirement[]` | FR-002 |
| `AcceptanceCriteriaGenerator` | 为可实施需求生成可验证条件 | `Requirement[]`, `NormalizedInput` | `AcceptanceCriterion[]` | FR-003 |
| `DependencyDetector` | 合并显式依赖并标记状态 | `NormalizedInput` | `Dependency[]` | FR-004 |
| `ClarificationManager` | 汇总缺失、模糊和冲突信息 | 各模块发现项 | `Clarification[]` | FR-005 |
| `AnalysisValidator` | 校验唯一性、关联、完整性和事实来源 | 候选结果 | `ValidationIssue[]` | FR-002, FR-003, FR-005, FR-006 |
| `ResultAssembler` | 生成稳定的完整输出，不省略空章节 | 各模块结果 | `AnalysisResult` | FR-006 |

### 4.1 依赖方向

```text
Transport Adapter -> AnalysisApplicationService -> Domain Ports
                                                -> Domain Services
Infrastructure Adapter ------------------------> Domain Ports
```

领域模型与校验规则不依赖 HTTP、数据库或具体分析引擎。适配器负责协议和供应商格式转换。

## 5. 显式接口

以下为语言无关的 TypeScript 风格契约。实现可映射为其他语言中的接口和不可变数据对象。

```ts
interface AnalysisService {
  analyze(command: AnalyzeCommand): Promise<AnalysisResult>;
}

interface RequirementDecomposer {
  decompose(input: NormalizedInput): Promise<DecompositionOutput>;
}

interface AcceptanceCriteriaGenerator {
  generate(
    input: NormalizedInput,
    requirements: Requirement[]
  ): Promise<CriteriaOutput>;
}

interface DependencyDetector {
  detect(input: NormalizedInput): Promise<DependencyOutput>;
}

interface AnalysisValidator {
  validate(candidate: AnalysisResult): ValidationIssue[];
}

interface AnalysisResultRepository {
  save(result: AnalysisResult): Promise<void>;
  findById(analysisId: string): Promise<AnalysisResult | null>;
}
```

`AnalysisResultRepository` 是可选端口。首版若不要求历史查询，不注入该端口，也不提供查询能力。

### 5.1 应用服务行为

```ts
class AnalysisApplicationService implements AnalysisService {
  constructor(
    normalizer: InputNormalizer,
    decomposer: RequirementDecomposer,
    criteriaGenerator: AcceptanceCriteriaGenerator,
    dependencyDetector: DependencyDetector,
    clarificationManager: ClarificationManager,
    validator: AnalysisValidator,
    assembler: ResultAssembler,
    repository?: AnalysisResultRepository
  );

  analyze(command: AnalyzeCommand): Promise<AnalysisResult>;
}
```

处理顺序：

1. 规范化并验证请求。
2. 空输入时直接生成“缺少原始业务需求”的待澄清结果。
3. 非空输入并行执行候选需求拆解与依赖识别。
4. 基于候选需求生成验收条件。
5. 汇总分析阶段发现的缺失、歧义和冲突。
6. 组装结果并执行确定性校验。
7. 存在阻断性校验错误时返回契约错误，不发布不完整结果。
8. 可选地保存通过校验的结果。

## 6. API 契约

传输协议尚未确认。若采用 HTTP，建议提供以下最小接口；其他协议应保持相同语义。

### 6.1 创建分析

`POST /v1/analyses`

请求：

```json
{
  "rawRequirement": "非空业务需求文本",
  "dependencies": [
    {
      "name": "调用方明确提供的依赖名称",
      "type": "external_system",
      "description": "可选说明"
    }
  ],
  "source": {
    "type": "user_input",
    "reference": "可选的外部文档或工单标识"
  }
}
```

成功响应：`200 OK`

```json
{
  "analysisId": "AN-唯一标识",
  "status": "completed",
  "goal": "从输入提取的目标；无法确定时明确说明",
  "requirements": [],
  "acceptanceCriteria": [],
  "dependencies": [],
  "clarifications": [],
  "validation": {
    "valid": true,
    "issues": []
  }
}
```

空输入不是传输格式错误。服务返回 `200 OK` 和结构完整的结果，其中需求与验收条件为空，待澄清项至少包含缺少原始业务需求、目标角色、场景、范围、规则及非功能约束。

格式错误返回：`400 Bad Request`

```json
{
  "code": "INVALID_REQUEST",
  "message": "请求无法解析或字段类型不符合契约",
  "details": [
    { "path": "dependencies[0].type", "reason": "unsupported_value" }
  ]
}
```

内部分析结果未通过结构校验返回：`422 Unprocessable Entity`

```json
{
  "code": "INVALID_ANALYSIS_RESULT",
  "message": "候选分析结果未通过完整性校验",
  "details": [
    { "rule": "CRITERION_REQUIREMENT_REFERENCE", "entityId": "AC-001" }
  ]
}
```

### 6.2 可选历史查询

仅当确认需要持久化时启用：

`GET /v1/analyses/{analysisId}`

- `200 OK`：返回 `AnalysisResult`。
- `404 Not Found`：不存在对应分析。
- 未启用仓储时不暴露该路由。

## 7. 数据模型

### 7.1 输入模型

```ts
type DependencyType =
  | "external_system"
  | "interface"
  | "data"
  | "permission"
  | "infrastructure"
  | "prerequisite_feature"
  | "delivery";

interface AnalyzeCommand {
  rawRequirement?: string | null;
  dependencies?: SuppliedDependency[];
  source?: InputSource;
}

interface SuppliedDependency {
  name: string;
  type: DependencyType;
  description?: string;
}

interface InputSource {
  type: "user_input" | "document" | "ticket" | "other";
  reference?: string;
}

interface NormalizedInput {
  rawRequirement: string;
  suppliedDependencies: SuppliedDependency[];
  source: InputSource;
  isEmpty: boolean;
}
```

### 7.2 输出与领域模型

```ts
type AnalysisStatus = "completed" | "needs_clarification";
type RequirementKind = "system_behavior" | "business_rule" | "quality_constraint";
type RequirementState = "implementable" | "needs_clarification";
type DependencyStatus = "confirmed" | "pending_confirmation" | "none_known";
type Severity = "error" | "warning";

interface AnalysisResult {
  analysisId: string;
  status: AnalysisStatus;
  goal: string;
  requirements: Requirement[];
  acceptanceCriteria: AcceptanceCriterion[];
  dependencies: Dependency[];
  clarifications: Clarification[];
  validation: ValidationSummary;
}

interface Requirement {
  id: string;                         // 本次结果内唯一，如 FR-001
  statement: string;                  // 使用“应”表达强制要求
  kind: RequirementKind;
  state: RequirementState;
  sourceRefs: SourceReference[];      // 确定性事实至少一个来源
  acceptanceCriterionIds: string[];
}

interface AcceptanceCriterion {
  id: string;                         // 本次结果内唯一，如 AC-FR001-01
  requirementId: string;              // 必须引用存在的唯一需求
  precondition: string;               // Given 或语义等价内容
  trigger: string;                    // When 或语义等价内容
  expectedResult: string;             // Then，可观察且可判定
  scenario: "normal" | "exception" | "boundary" | "not_applicable";
  sourceRefs: SourceReference[];
}

interface Dependency {
  id: string;
  name: string;
  type?: DependencyType;
  status: DependencyStatus;
  description: string;
  sourceRefs: SourceReference[];
}

interface Clarification {
  id: string;                         // 本次结果内唯一，如 Q-001
  question: string;
  impact: string;
  relatedRequirementIds: string[];
  sourceRefs: SourceReference[];
}

interface SourceReference {
  sourceType: "raw_requirement" | "supplied_dependency" | "confirmed_constraint";
  locator: string;                    // 字符区间、字段路径或外部引用
  excerpt?: string;
}

interface ValidationSummary {
  valid: boolean;
  issues: ValidationIssue[];
}

interface ValidationIssue {
  severity: Severity;
  rule: string;
  entityId?: string;
  message: string;
}
```

### 7.3 标识与基数

- `analysisId`：全局唯一；格式可配置，不作为业务语义来源。
- `Requirement.id`、`AcceptanceCriterion.id`、`Dependency.id`、`Clarification.id`：在单个分析结果内唯一。
- 一个 `Requirement` 对应零到多个验收条件；仅 `needs_clarification` 状态允许为零。
- 一个 `AcceptanceCriterion` 必须且只能属于一个 `Requirement`。
- 空依赖输入且正文没有显式依赖时，输出一个 `status = none_known` 的依赖状态记录，确保章节不被静默省略。

## 8. 校验规则

| 规则编号 | 规则 | 失败级别 | 对应验收条件 |
|---|---|---|---|
| VAL-001 | 所有实体标识在各自集合内唯一且非空 | error | AC-FR002-01, AC-FR005-01 |
| VAL-002 | 可实施需求至少关联一条验收条件 | error | AC-FR003-01, AC-FR006-03 |
| VAL-003 | 验收条件引用的需求必须存在且仅有一个 | error | AC-FR003-05 |
| VAL-004 | 验收条件包含前置、触发、可观察结果 | error | AC-FR003-02, AC-FR003-03 |
| VAL-005 | 确定性需求至少包含一个有效来源引用 | error | AC-FR002-04 |
| VAL-006 | 待澄清项包含问题和影响 | error | AC-FR005-01 |
| VAL-007 | 所有必需输出集合存在，允许为空但不可缺失 | error | AC-FR006-01 |
| VAL-008 | 空输入不产生具体业务需求或规则 | error | AC-FR001-02 |
| VAL-009 | 模糊或冲突事实具有对应待澄清项 | warning | AC-FR002-05 |
| VAL-010 | 无已知依赖时不生成推断依赖 | error | AC-FR004-01 |

校验器只做可确定执行的结构和引用检查。“原子性”与“是否保持原意”需要分析器提供证据，并通过测试样例或人工评审补充验证。

## 9. 关键流程

### 9.1 正常输入

```text
调用方 -> ApplicationService: AnalyzeCommand
ApplicationService -> InputNormalizer: normalize
ApplicationService -> RequirementDecomposer: decompose
ApplicationService -> DependencyDetector: detect
ApplicationService -> CriteriaGenerator: generate
ApplicationService -> ClarificationManager: consolidate
ApplicationService -> ResultAssembler: assemble
ApplicationService -> AnalysisValidator: validate
ApplicationService --> 调用方: AnalysisResult
```

### 9.2 空输入

1. `InputNormalizer` 将缺失、空串或纯空白统一为 `isEmpty = true`。
2. 编排器跳过业务需求拆解和验收条件生成。
3. `ClarificationManager` 生成至少覆盖原始需求、目标角色、场景、范围、规则、非功能约束的问题。
4. 依赖输出为“无已知依赖”，除非调用方显式提供依赖。
5. 返回 `needs_clarification`，需求和验收条件集合为空。

### 9.3 候选结果不完整

1. 校验器返回 `severity = error` 的问题。
2. 结果不写入可选仓储。
3. 协议适配器返回 `INVALID_ANALYSIS_RESULT`，并记录规则编号，不向调用方暴露供应商内部信息。

## 10. 组件错误契约

领域端口使用稳定错误码，适配器负责映射为 HTTP 或其他协议状态。

| 错误码 | 产生位置 | 含义 | 可重试 |
|---|---|---|---|
| `INVALID_REQUEST` | 输入适配器 | 字段类型或枚举非法 | 否，修改输入后重试 |
| `ANALYZER_UNAVAILABLE` | 分析器适配器 | 可选分析实现不可用 | 是 |
| `INVALID_ANALYSIS_RESULT` | 校验器 | 候选结果违反领域不变量 | 否，修复分析实现 |
| `PERSISTENCE_FAILURE` | 可选仓储 | 保存或读取失败 | 取决于实现 |
| `ANALYSIS_NOT_FOUND` | 可选仓储 | 指定结果不存在 | 否 |

空业务文本属于有效但信息不足的分析输入，不使用 `INVALID_REQUEST`。

## 11. 实现建议

建议首版采用单体模块化服务：

```text
src/
  application/analysis-service
  domain/model
  domain/services
  domain/ports
  adapters/inbound
  adapters/analyzer
  adapters/persistence        # 确认需要历史记录后再添加
```

最小可交付实现只需要：一个调用适配器、一个 `AnalysisService`、分析端口实现、领域校验器和 DTO 序列化。暂不引入数据库、消息队列或微服务拆分。

## 12. 测试设计

| 测试层级 | 必测内容 |
|---|---|
| 单元测试 | 空白规范化、ID 唯一性、孤立验收条件、可实施需求无验收条件、无来源事实、澄清项字段完整性 |
| 契约测试 | 请求/响应字段、枚举、错误码、空集合仍被序列化 |
| 组件测试 | 非空输入完整流程、空输入短路流程、分析器不可用、候选结果校验失败 |
| 追踪测试 | FR-001 至 FR-006 的每条验收条件至少映射一个测试用例 |

在具体业务输入可用后，应增加正常、异常、边界及歧义样例集，验证拆解质量和原意保持。

## 13. 需求追踪矩阵

| 需求 | 主要模块 | 接口/模型 | 校验或流程 |
|---|---|---|---|
| FR-001 | `InputNormalizer`, `AnalysisApplicationService` | `AnalyzeCommand`, `NormalizedInput` | 空输入流程、VAL-008 |
| FR-002 | `RequirementDecomposer` | `Requirement`, `SourceReference` | VAL-001, VAL-005, VAL-009 |
| FR-003 | `AcceptanceCriteriaGenerator` | `AcceptanceCriterion` | VAL-002, VAL-003, VAL-004 |
| FR-004 | `DependencyDetector` | `Dependency` | VAL-010 |
| FR-005 | `ClarificationManager` | `Clarification` | VAL-006, 空输入流程 |
| FR-006 | `ResultAssembler`, `AnalysisValidator` | `AnalysisResult` | VAL-007、完整流程 |

## 14. 架构决策与待澄清项

### 已确定

- 采用模块化单体作为首版逻辑边界。
- 核心分析能力、传输协议和基础设施通过接口解耦。
- 分析结果必须先通过确定性校验再返回或持久化。
- 当前依赖状态为“无已知依赖”。

### 尚待确认

- **ARC-Q-001 运行形态**：库、命令行、HTTP 服务或现有系统内模块；影响入站适配器。
- **ARC-Q-002 分析实现**：规则、人工、模型或混合方式；影响准确性、成本及故障处理。
- **ARC-Q-003 持久化**：是否需要历史查询、审计和版本管理；影响仓储与查询接口。
- **ARC-Q-004 安全与合规**：输入是否包含敏感数据及保留策略；影响脱敏、访问控制和日志。
- **ARC-Q-005 非功能指标**：吞吐、延迟、可用性和结果规模；影响部署和容量设计。
- **ARC-Q-006 语言与格式**：是否只处理中文及是否需要 Markdown/JSON 双输出；影响解析与序列化。

## 15. 交付状态

- [x] 已定义系统边界和模块职责。
- [x] 已定义应用、领域和可选基础设施接口。
- [x] 已定义输入、输出、实体、枚举和错误数据模型。
- [x] 已定义关键流程、领域不变量和错误契约。
- [x] 已建立 FR-001 至 FR-006 的架构追踪。
- [x] 未把未确认的业务规则或外部依赖写成既定事实。

**交付状态：`architecture_written = 通过`。**
