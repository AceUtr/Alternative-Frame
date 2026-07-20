export type ScenarioType = "HAPPY_PATH" | "EXCEPTION" | "BOUNDARY" | "NOT_APPLICABLE";
export type Severity = "WARNING" | "ERROR";

export interface SourceInput {
  sourceId: string;
  title?: string;
  content: string;
}

export interface SuppliedDependency {
  type?: Dependency["type"];
  name: string;
  description?: string;
}

export interface CreateAnalysisCommand {
  sources: SourceInput[];
  dependencies?: SuppliedDependency[] | Record<string, string>;
  locale?: string;
}

export interface SourceReference {
  sourceId: string;
  quote?: string;
}

export interface RecognizedItem {
  text: string;
  sourceReferences: SourceReference[];
}

export interface RecognizedContext {
  businessGoals: RecognizedItem[];
  actors: RecognizedItem[];
  scenarios: RecognizedItem[];
  functionalScope: RecognizedItem[];
  businessRules: RecognizedItem[];
  inputs: RecognizedItem[];
  outputs: RecognizedItem[];
  exceptionScenarios: RecognizedItem[];
  constraints: RecognizedItem[];
  externalDependencies: RecognizedItem[];
}

export interface Requirement {
  id: string;
  name: string;
  statement: string;
  trigger: string | null;
  processing: string | null;
  expectedOutcome: string | null;
  state: "DEFINED" | "NEEDS_CLARIFICATION";
  category: "FUNCTIONAL" | "QUALITY" | "CONSTRAINT";
  sourceReferences: SourceReference[];
  dependencyIds: string[];
  clarificationIds: string[];
}

export interface AcceptanceCriterion {
  id: string;
  requirementId: string;
  title: string;
  scenarioType: ScenarioType;
  given: string;
  when: string;
  then: string;
}

export interface Dependency {
  id: string;
  type: "EXTERNAL_SYSTEM" | "API" | "DATA" | "PERMISSION" | "PREREQUISITE" | "BUSINESS_DECISION";
  name?: string;
  description: string;
  confirmationStatus: "CONFIRMED" | "CONFIRMATION_REQUIRED";
  sourceReferences: SourceReference[];
}

export interface DependencyReport {
  status: "HAS_DEPENDENCIES" | "NONE_KNOWN";
  displayText: string;
  items: Dependency[];
}

export interface Clarification {
  id: string;
  category?: "BUSINESS_GOAL" | "ACTOR" | "SCENARIO" | "SCOPE" | "BUSINESS_RULE" | "INPUT_OUTPUT" | "EXCEPTION" | "CONSTRAINT" | "DEPENDENCY" | "NON_FUNCTIONAL";
  question: string;
  impact: string;
  relatedRequirementIds: string[];
  sourceReferences: SourceReference[];
}

export interface ValidationIssue {
  code: string;
  path: string;
  severity: Severity;
  message: string;
}

export interface AnalysisResult {
  taskId: string;
  objective: string;
  recognizedContext: RecognizedContext;
  requirements: Requirement[];
  acceptanceCriteria: AcceptanceCriterion[];
  dependencies: Dependency[];
  dependencyReport: DependencyReport;
  clarifications: Clarification[];
  assumptions: [];
  validationIssues: ValidationIssue[];
  generatedAt: string;
}
