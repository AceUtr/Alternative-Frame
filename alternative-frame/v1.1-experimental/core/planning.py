from __future__ import annotations 

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

from .models import Plan, SubTask


@dataclass
class Intent:
    goal: str
    domain: str
    deliverables: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    quality_requirements: List[str] = field(default_factory=list)
    risk_level: str = "medium"
    budget: Dict[str, int] = field(default_factory=lambda: {"max_steps": 100, "max_retries": 2})


@dataclass
class AcceptanceCheck:
    id: str
    description: str
    check_type: str  # manual / command / file_exists / metric
    required: bool = True
    command: str | None = None
    threshold: float | None = None


@dataclass
class TaskDraft:
    id: str
    role: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    expected_outputs: List[str] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    checks: List[AcceptanceCheck] = field(default_factory=list)


class IntentParser:
    """Deterministic v0 parser; later replace internals with JSON-schema LLM output."""

    def parse(self, user_goal: str) -> Intent:
        if not user_goal or not user_goal.strip():
            raise ValueError("user_goal cannot be empty")
        text = user_goal.strip()
        lowered = text.lower()
        software_words = ("软件", "代码", "服务", "api", "fastapi", "测试", "开发", "工程", "software")
        research_words = ("研究", "实验", "模型", "训练", "指标", "论文", "科研", "research", "experiment")
        if any(word in text or word in lowered for word in software_words) or "计算器" in text or "calculator" in lowered:
            domain = "software_engineering"
        elif any(word in text or word in lowered for word in research_words):
            domain = "research"
        else:
            domain = "general"
        deliverables = []
        for word, item in [("测试", "tests"), ("文档", "documentation"), ("部署", "deployment"), ("报告", "report"), ("代码", "source_code")]:
            if word in text:
                deliverables.append(item)
        return Intent(goal=text, domain=domain, deliverables=deliverables)


class TaskDecomposer:
    """Convert an Intent into domain-specific task drafts."""

    def decompose(self, intent: Intent) -> List[TaskDraft]:
        if intent.domain == "software_engineering":
            return self._software(intent)
        if intent.domain == "research":
            return self._research(intent)
        return [TaskDraft("analyze", "analyst", intent.goal, expected_outputs=["analysis"])]

    def _research(self, intent: Intent) -> List[TaskDraft]:
        return [
            TaskDraft("research", "researcher", "分析研究目标、已有方案和实验假设", expected_outputs=["research_plan.md"], required_tools=["file_editor"]),
            TaskDraft("baseline", "experimenter", "确认基线、运行环境和可复现实验", expected_outputs=["baseline.json"], required_tools=["shell_runner", "experiment_runner"]),
            TaskDraft("experiment", "experimenter", "执行实验、记录指标并保存产物", depends_on=["research", "baseline"], expected_outputs=["results.tsv"], required_tools=["shell_runner", "experiment_runner"]),
            TaskDraft("review", "reviewer", "检查实验结果、证据和结论", depends_on=["experiment"], expected_outputs=["review.md"], required_tools=["file_editor"]),
        ]

    def _software(self, intent: Intent) -> List[TaskDraft]:
        lowered = intent.goal.lower()
        if "计算器" in intent.goal or "calculator" in lowered:
            return [
                TaskDraft(
                    "implementation",
                    "developer",
                    f"{intent.goal}。交付可直接运行的 PowerShell 科学计算器：引擎写入 src/CalculatorEngine.psm1，交互式命令行入口写入 calculator.ps1。支持 + - * / % ^、括号、正负号、pi/e/ans、sin/cos/tan、反三角函数、sqrt、abs、ln/log/exp，并提供角度/弧度模式。表达式必须由解析器计算，禁止 Invoke-Expression 或执行用户输入。兼容 Windows PowerShell 5.1 与 PowerShell 7。先写这两个正式文件；不要创建临时原型、额外测试脚本或做环境探测，工作区已确认有 PowerShell。",
                    expected_outputs=["src/CalculatorEngine.psm1", "calculator.ps1"],
                    required_tools=["file_editor", "shell_runner"],
                    checks=[AcceptanceCheck(
                        "calculator_engine_created",
                        "本次运行生成 PowerShell 计算器引擎",
                        "file_exists",
                        command=None,
                    )],
                ),
                TaskDraft(
                    "tests",
                    "tester",
                    "实现文件已经存在。只创建 tests/test_calculator.ps1，不要修改实现；用严格失败模式测试四则运算、括号与优先级、幂运算、pi/e/ans、三角函数和角度/弧度、非法表达式与除零。测试脚本必须在任一断言失败时抛错并返回非零退出码。随后运行且只以此命令作为验收命令：pwsh -NoProfile -File tests/test_calculator.ps1。不要创建临时测试或探测环境。",
                    depends_on=["implementation"],
                    expected_outputs=["tests/test_calculator.ps1"],
                    required_tools=["file_editor", "shell_runner", "test_runner"],
                    checks=[
                        AcceptanceCheck(
                            "calculator_tests_created",
                            "本次运行生成针对性 PowerShell 测试",
                            "file_exists",
                        ),
                        AcceptanceCheck(
                            "calculator_tests_pass",
                            "PowerShell 计算器测试命令退出码为 0",
                            "command",
                            command="pwsh -NoProfile -File tests/test_calculator.ps1",
                        ),
                    ],
                ),
            ]
        return [
            TaskDraft("requirements", "analyst", "拆解需求并生成验收条件", expected_outputs=["requirements.md"], required_tools=["file_editor"]),
            TaskDraft("architecture", "architect", "设计模块、接口和数据模型", depends_on=["requirements"], expected_outputs=["architecture.md"], required_tools=["file_editor"]),
            TaskDraft("tests", "tester", "编写需求测试和回归测试", depends_on=["requirements"], expected_outputs=["tests/"], required_tools=["file_editor", "shell_runner"]),
            TaskDraft("implementation_auth", "developer", "实现用户注册、登录和认证相关功能，并完成局部检查", depends_on=["architecture", "tests"], expected_outputs=["src/"], required_tools=["file_editor", "shell_runner", "git_client"]),
            TaskDraft("implementation_service", "developer", "实现核心业务接口、数据模型和错误处理，并完成局部检查", depends_on=["architecture", "tests"], expected_outputs=["src/"], required_tools=["file_editor", "shell_runner", "git_client"]),
            TaskDraft("integration", "tester", "合并检查实现并运行完整自动化测试", depends_on=["implementation_auth", "implementation_service"], expected_outputs=["test-report.json"], required_tools=["shell_runner", "test_runner"]),
            TaskDraft("review", "reviewer", "执行最终测试、构建和代码审查", depends_on=["integration"], expected_outputs=["test-report.json"], required_tools=["test_runner"]),
        ]


class AcceptanceCriteriaGenerator:
    """Generate executable checks for each draft and final plan checks."""

    def generate(self, intent: Intent, drafts: Sequence[TaskDraft]) -> Sequence[TaskDraft]:
        for task in drafts:
            if task.id == "requirements":
                task.checks = [AcceptanceCheck("requirements_written", "需求和约束已记录", "file_exists")]
            elif task.id == "architecture":
                task.checks = [AcceptanceCheck("architecture_written", "架构设计已记录", "file_exists")]
            elif task.id == "tests":
                if not task.checks:
                    task.checks = [AcceptanceCheck("tests_created", "测试文件已创建", "file_exists")]
            elif task.id.startswith("implementation"):
                task.checks = [AcceptanceCheck("implementation_present", "源代码已生成", "file_exists")]
            elif task.id == "integration":
                task.checks = [AcceptanceCheck("tests_pass", "完整自动化测试通过", "command", command="pytest -q")]
            elif task.id == "review" and intent.domain == "software_engineering":
                task.checks = [AcceptanceCheck("tests_pass", "自动化测试通过", "command", command="pytest -q")]
            elif task.id == "research":
                task.checks = [AcceptanceCheck("research_plan_written", "研究计划和假设已记录", "file_exists")]
            elif task.id == "baseline":
                task.checks = [AcceptanceCheck("baseline_recorded", "基线结果已记录", "metric")]
            elif task.id == "experiment":
                task.checks = [AcceptanceCheck("experiment_recorded", "实验指标和产物已记录", "metric")]
            elif task.id == "review" and intent.domain == "research":
                task.checks = [AcceptanceCheck("evidence_checked", "结果证据已检查", "file_exists")]
            if not task.checks:
                task.checks = [AcceptanceCheck(f"{task.id}_completed", "子任务完成并有产物", "manual")]
        return drafts


class Planner:
    """Validate drafts and build the executable Plan consumed by Orchestrator."""

    def build(self, intent: Intent, drafts: Sequence[TaskDraft]) -> Plan:
        if not drafts:
            raise ValueError("Planner received no task drafts")
        ids = {task.id for task in drafts}
        for task in drafts:
            missing = set(task.depends_on) - ids
            if missing:
                raise ValueError(f"{task.id} depends on unknown tasks: {sorted(missing)}")
            if not task.role or not task.description:
                raise ValueError(f"Task {task.id} must have a role and description")
        subtasks = [
            SubTask(
                id=task.id,
                role=task.role,
                description=task.description,
                depends_on=list(task.depends_on),
                acceptance=[check.id for check in task.checks],
                metadata={
                    "expected_outputs": task.expected_outputs,
                    "required_tools": task.required_tools,
                    "checks": [check.__dict__ for check in task.checks],
                },
            )
            for task in drafts
        ]
        final_checks = [check.id for task in drafts for check in task.checks if task.id in ("review", "experiment", "integration") or task.id.startswith("implementation")]
        plan = Plan(intent.goal, subtasks, final_acceptance=final_checks)
        plan.validate()
        return plan


class PlanningPipeline:
    """Convenience facade for the four planning stages."""

    def __init__(self):
        self.intent_parser = IntentParser()
        self.decomposer = TaskDecomposer()
        self.acceptance_generator = AcceptanceCriteriaGenerator()
        self.planner = Planner()

    def build(self, user_goal: str) -> Plan:
        intent = self.intent_parser.parse(user_goal)
        drafts = self.decomposer.decompose(intent)
        drafts = self.acceptance_generator.generate(intent, drafts)
        return self.planner.build(intent, drafts)
