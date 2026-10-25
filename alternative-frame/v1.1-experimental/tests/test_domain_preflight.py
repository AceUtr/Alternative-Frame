from pathlib import Path

from core.agents import DeterministicAgent
from core.domains import DomainAdapter, DomainRegistry
from core.long_horizon import AcceptanceContract, GoalCriterion
from core.models import Plan, SubTask
from core.preflight import HarnessPreflightChecker
from core.tools import Tool, ToolRegistry, ToolResult


class NoopTool(Tool):
    name = "noop"

    def schema(self):
        return {"type": "function", "function": {"name": self.name, "parameters": {"type": "object"}}}

    def execute(self, arguments):
        return ToolResult(self.name, True, output="ok")


class ExampleAdapter(DomainAdapter):
    name = "example"

    def register_tools(self, registry, workspace):
        registry.register(NoopTool())

    def build_agents(self, model_client, tools):
        return [DeterministicAgent("worker")]

    def build_plan(self, goal):
        return Plan(
            goal,
            [SubTask("work", "worker", "work", metadata={"required_tools": ["noop"]})],
        )

    def build_contract(self, goal):
        return AcceptanceContract(
            goal=goal,
            goal_summary="Complete the example task",
            criteria=[GoalCriterion("done", "Work is verified", "manual")],
        )


def test_adapter_configures_agents_and_tools_and_passes_preflight(tmp_path):
    adapter = ExampleAdapter()
    domains = DomainRegistry([adapter])
    tools, agents = adapter.configure(tmp_path)
    plan = adapter.build_plan("example goal")

    report = HarnessPreflightChecker().check(
        domains=domains,
        domain="example",
        plan=plan,
        agents=agents,
        tools=tools,
        workspace=tmp_path,
        contract=adapter.build_contract(plan.goal),
        model_probe=lambda: (True, "connected"),
    )

    assert report.ready
    assert agents.roles() == ("worker",)
    assert tools.names() == ("noop",)
    assert "model_connection=ok" in report.checks


def test_preflight_reports_missing_domain_role_tool_and_contract(tmp_path):
    plan = Plan(
        "goal",
        [SubTask("work", "missing-role", "work", metadata={"required_tools": ["missing-tool"]})],
    )

    report = HarnessPreflightChecker().check(
        domains=DomainRegistry(),
        domain="missing-domain",
        plan=plan,
        agents=ExampleAdapter().configure(tmp_path)[1],
        tools=ToolRegistry(),
        workspace=tmp_path,
        contract=None,
    )

    assert not report.ready
    assert {issue.code for issue in report.issues} == {
        "domain_not_registered",
        "missing_agent_roles",
        "missing_tools",
        "contract_missing",
    }


def test_domain_registry_rejects_duplicate_names():
    domains = DomainRegistry([ExampleAdapter()])

    try:
        domains.register(ExampleAdapter())
    except ValueError as exc:
        assert "already registered" in str(exc)
    else:
        raise AssertionError("duplicate domains must be rejected")
