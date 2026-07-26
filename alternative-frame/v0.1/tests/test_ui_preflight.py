from core.agents import AgentRegistry, DeterministicAgent
from core.long_horizon import AcceptanceContract, GoalCriterion
from core.models import Plan, SubTask
from ui import UIRuntimeDomainAdapter, run_ui_preflight


def contract_for(goal):
    return AcceptanceContract(
        goal=goal,
        goal_summary="Verify the UI task",
        criteria=[GoalCriterion("verified", "Task is verified", "manual")],
    )


def test_ui_runtime_adapter_preserves_prepared_plan_and_contract():
    plan = Plan("goal", [SubTask("work", "worker", "work")])
    contract = contract_for(plan.goal)
    adapter = UIRuntimeDomainAdapter("software", plan, contract)

    assert adapter.name == "software"
    assert adapter.build_plan(plan.goal) is plan
    assert adapter.build_contract(plan.goal) is contract


def test_ui_preflight_blocks_a_missing_agent_before_execution(tmp_path):
    plan = Plan("goal", [SubTask("work", "missing", "work")])

    report = run_ui_preflight(
        domain="software",
        plan=plan,
        contract=contract_for(plan.goal),
        agents=AgentRegistry(),
        workspace=tmp_path,
    )

    assert not report.ready
    assert any(issue.code == "missing_agent_roles" for issue in report.issues)


def test_ui_preflight_accepts_a_complete_stub_runtime(tmp_path):
    plan = Plan("goal", [SubTask("work", "worker", "work")])
    agents = AgentRegistry()
    agents.register(DeterministicAgent("worker"))

    report = run_ui_preflight(
        domain="software",
        plan=plan,
        contract=contract_for(plan.goal),
        agents=agents,
        workspace=tmp_path,
    )

    assert report.ready
