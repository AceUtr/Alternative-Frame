from core.main_agent import MainAgent
from core.agents import AgentRegistry, DeterministicAgent
from core.orchestrator import Orchestrator


def test_software_demo_execution():

    registry = AgentRegistry()


    roles = [
        "analyst",
        "architect",
        "tester",
        "developer",
        "reviewer",
    ]


    for role in roles:
        registry.register(
            DeterministicAgent(
                role=role
            )
        )


    orchestrator = Orchestrator(
        registry
    )


    agent = MainAgent(
        orchestrator
    )


    goal = """
    Analyze software project,
    find bugs,
    modify code,
    run tests.
    """


    report = agent.execute(goal)


    assert report.status == "success"

    assert len(report.results) > 0
