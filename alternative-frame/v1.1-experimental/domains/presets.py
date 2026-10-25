from core.agents import AgentRegistry, DeterministicAgent
from core.models import Plan, SubTask


def research_plan() -> Plan:
    return Plan(
        goal="run a reproducible research experiment",
        subtasks=[
            SubTask("research", "researcher", "analyze the research direction", acceptance=["hypothesis_written"]),
            SubTask("baseline", "experimenter", "verify the baseline experiment", acceptance=["baseline_recorded"]),
            SubTask("review", "reviewer", "review research evidence", depends_on=["research", "baseline"], acceptance=["evidence_checked"]),
        ],
        final_acceptance=["review_complete"],
    )


def software_plan() -> Plan:
    return Plan(
        goal="deliver a tested software change",
        subtasks=[
            SubTask("requirements", "analyst", "extract requirements and acceptance checks", acceptance=["requirements_written"]),
            SubTask("architecture", "architect", "design the implementation", depends_on=["requirements"], acceptance=["design_written"]),
            SubTask("tests", "tester", "prepare acceptance tests", depends_on=["requirements"], acceptance=["tests_written"]),
            SubTask("implementation", "developer", "implement the change", depends_on=["architecture", "tests"], acceptance=["tests_pass"]),
            SubTask("review", "reviewer", "review implementation and test evidence", depends_on=["implementation"], acceptance=["review_complete"]),
        ],
        final_acceptance=["tests_pass", "review_complete"],
    )


def demo_registry() -> AgentRegistry:
    registry = AgentRegistry()
    for role in ["researcher", "experimenter", "reviewer", "analyst", "architect", "developer", "tester"]:
        registry.register(DeterministicAgent(role))
    return registry

