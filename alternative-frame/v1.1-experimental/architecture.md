# 架构设计

## 1. 设计范围

本设计面向当前任务合同所定义的文档交付流程：读取上游需求、生成架构文档，并以精确路径的文件存在性作为必选验收条件。

当前没有具体产品、用户流程、外部系统或业务数据需求，因此不设计虚构的业务服务、数据库或网络 API。后续获得业务需求时，应在本文第 8 节所定义的扩展边界内补充领域架构。

## 2. 架构目标

- 在工作区根目录生成唯一必需交付物 `architecture.md`。
- 使用 `file_editor` 完成所有工作区读写操作。
- 将输入解析、架构建模、文档持久化和验收校验分离，便于定位失败。
- 对路径、工具、重试和完成条件采用显式约束。
- 在缺少业务上下文时保持最小实现，不引入运行时服务或基础设施。

## 3. 系统上下文

```text
requirements.md
      |
      v
[Requirements Reader]
      |
      v
[Architecture Composer]
      |
      v
[Artifact Writer] --file_editor.write--> architecture.md
      |
      v
[Acceptance Verifier] --file_editor.read--> pass / fail
```

### 3.1 外部参与者

| 参与者 | 输入 | 输出 | 责任 |
|---|---|---|---|
| 上游需求任务 | `requirements.md` | 已记录的需求和约束 | 提供设计依据 |
| 架构任务执行器 | 任务合同、依赖摘要 | `architecture.md` | 生成并验证架构设计 |
| 验收器 | 预期路径和检查定义 | 通过或失败 | 判断交付物是否存在 |

## 4. 模块设计

### 4.1 Requirements Reader

**职责：**读取并归纳 `requirements.md`，识别已知需求、约束、验收条件和信息缺口。

**输入接口：**

```text
read(path: "requirements.md") -> FileReadResult
```

**输出模型：**

```text
RequirementContext {
  sourcePath: string
  requirements: Requirement[]
  constraints: Constraint[]
  acceptanceChecks: AcceptanceCheck[]
  assumptions: string[]
  gaps: string[]
}
```

**失败条件：**文件不存在、不可读取或内容无法形成最小设计上下文。若依赖仅以任务摘要提供，可记录该摘要并继续，但必须标明来源限制。

### 4.2 Architecture Composer

**职责：**将任务合同和 `RequirementContext` 转换为结构化架构文档。

**接口：**

```text
compose(contract: TaskContract, context: RequirementContext) -> ArchitectureDocument
```

**约束：**

- 必须覆盖模块、接口、数据模型、执行流程、错误处理、验收映射和风险。
- 不得把未提供的业务能力表述为已确认需求。
- 输出必须是可写入单个 Markdown 文件的文本内容。

### 4.3 Artifact Writer

**职责：**将架构文档写入合同指定的精确相对路径。

**输入接口：**

```text
write(path: "architecture.md", content: string) -> FileWriteResult
```

**不变量：**

- `path` 必须严格等于 `architecture.md`。
- 写入工具必须为 `file_editor`。
- 不生成替代文件名或额外交付物。

### 4.4 Acceptance Verifier

**职责：**验证必需交付物已创建且可读取。

**接口：**

```text
verify(check: AcceptanceCheck, artifact: ArtifactSpec) -> VerificationResult
```

当前检查实现：

```text
verifyFileExists("architecture.md") -> {
  checkId: "architecture_written"
  passed: boolean
  evidence: string
}
```

由于工具没有独立的 `exists` 操作，使用 `file_editor.read` 成功作为“文件存在且可读取”的证据。读取失败即检查失败。

## 5. 数据模型

### 5.1 任务合同

```text
TaskContract {
  taskId: string                 // 当前为 "architecture"
  role: string                   // 当前为 "architect"
  description: string
  requiredTools: string[]        // 当前必须包含 "file_editor"
  expectedOutputs: ArtifactSpec[]
  acceptanceChecks: AcceptanceCheck[]
  maxRetries: integer
}
```

### 5.2 交付物定义

```text
ArtifactSpec {
  path: string                   // "architecture.md"
  format: "markdown"
  required: boolean
  ownerTaskId: string
}
```

### 5.3 验收检查

```text
AcceptanceCheck {
  id: string                    // "architecture_written"
  description: string
  type: "file_exists"
  required: boolean
  command: string | null
  threshold: number | null
}
```

### 5.4 操作结果

```text
FileReadResult {
  success: boolean
  path: string
  content: string | null
  error: string | null
}

FileWriteResult {
  success: boolean
  path: string
  error: string | null
}

VerificationResult {
  checkId: string
  passed: boolean
  artifactPath: string
  evidence: string
  exitCode: integer | null
}
```

`exitCode` 在当前文件存在性检查中为 `null`，因为合同没有提供命令型检查。

### 5.5 执行状态

```text
ExecutionState =
  | "INPUT_PENDING"
  | "INPUT_READY"
  | "DOCUMENT_COMPOSED"
  | "ARTIFACT_WRITTEN"
  | "VERIFIED"
  | "FAILED"
```

允许的状态迁移：

```text
INPUT_PENDING -> INPUT_READY -> DOCUMENT_COMPOSED
-> ARTIFACT_WRITTEN -> VERIFIED

任一步骤失败 -> FAILED
FAILED -> 最近失败步骤（仅在重试预算内且计划已调整）
```

## 6. 执行流程

1. 校验任务合同包含预期输出 `architecture.md` 和必选检查 `architecture_written`。
2. 通过 `file_editor.read` 读取 `requirements.md`。
3. 提取约束；若无业务需求，将范围明确限制为任务执行架构。
4. 生成包含显式模块、接口和数据模型的 Markdown 文档。
5. 通过 `file_editor.write` 写入精确路径 `architecture.md`。
6. 通过一次新的 `file_editor.read` 回读该文件。
7. 回读成功则将 `architecture_written` 标记为通过并停止工具调用；回读失败则进入失败处理。
8. 最终报告已完成工作、交付物路径、检查结果和剩余风险。

## 7. 错误处理与重试

| 故障 | 处理 | 是否可重试 |
|---|---|---|
| `requirements.md` 不存在或不可读 | 使用依赖摘要建立受限上下文，并在风险中记录 | 是，前提是调整读取或输入策略 |
| `architecture.md` 写入失败 | 保留错误信息，检查路径和内容后再写入 | 是，最多受 `maxRetries` 限制 |
| 回读失败 | 不声明完成，修正写入问题后重新验证 | 是，最多受 `maxRetries` 限制 |
| 缺少业务需求 | 采用最小任务架构，不猜测业务模块 | 否，这不是执行错误 |
| 未提供命令检查 | 记录为不适用，不生成虚假退出码 | 否 |

重试必须满足两个条件：前一次操作失败，且新的调用参数或执行计划已发生有效调整。成功后不得重复相同工具调用。

## 8. 业务架构扩展接口

获得具体业务需求后，可在不改变当前交付流程的前提下增加以下模型：

```text
DomainModule {
  name: string
  responsibility: string
  providedInterfaces: InterfaceSpec[]
  requiredInterfaces: InterfaceSpec[]
  ownedEntities: EntitySpec[]
}

InterfaceSpec {
  name: string
  protocol: "in_process" | "http" | "event" | "file"
  inputSchema: string
  outputSchema: string
  errors: string[]
}

EntitySpec {
  name: string
  fields: FieldSpec[]
  invariants: string[]
  lifecycle: string[]
}
```

扩展时必须先从业务需求建立领域边界，再决定是否需要数据库、消息系统或网络服务；这些基础设施不属于当前已确认范围。

## 9. 验收映射

| 验收检查 | 架构实现 | 通过证据 |
|---|---|---|
| `architecture_written` | Artifact Writer 写入 `architecture.md`，Acceptance Verifier 回读 | `file_editor.read` 对 `architecture.md` 返回成功 |
| 精确输出路径 | `ArtifactSpec.path` 固定为 `architecture.md` | 回读路径与合同路径一致 |
| 使用指定工具 | 文件读写接口仅绑定 `file_editor` | 工具调用记录 |
| 不以说明替代交付物 | 先写入并验证，后输出完成说明 | 文件内容可读取 |

## 10. 架构决策与风险

### 决策

- 采用单文件 Markdown 交付，不引入应用运行时、数据库或部署拓扑。
- 将回读成功作为文件存在性证据，适配现有 `file_editor` 接口。
- 对未知业务范围使用显式扩展接口，而不是提前设计具体领域模块。

### 剩余风险

- 上游需求只描述任务合同，无法验证任何具体业务架构是否满足真实用户需求。
- 合同的自动验收仅检查文件存在性，不能自动评估架构内容的正确性和完整性。
- 若后续业务需求引入性能、安全、可用性或合规目标，需要重新评估模块边界和基础设施选择。
