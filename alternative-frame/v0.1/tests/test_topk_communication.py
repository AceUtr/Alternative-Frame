from core.agents import AgentRegistry, DeterministicAgent
from core.communication import TopKCommunicationRouter
from core.models import AgentResult, Plan, SubTask
from core.orchestrator import Orchestrator


def _result(task_id, summary, artifacts=None):
    return AgentResult(task_id, "success", summary=summary, artifacts=artifacts or [])


def test_router_keeps_dependencies_and_selects_top_k_relevant_peers():
    tasks = {
        "required": SubTask("required", "analyst", "requirements"),
        "security": SubTask("security", "reviewer", "JWT security review"),
        "database": SubTask("database", "architect", "database schema"),
        "target": SubTask(
            "target",
            "developer",
            "implement JWT authentication",
            depends_on=["required"],
            inputs=["security.md"],
            metadata={"communication_top_k": 1, "communication_topics": ["JWT"]},
        ),
    }
    completed = {
        "required": _result("required", "requirements done"),
        "security": _result("security", "JWT risks", ["security.md"]),
        "database": _result("database", "tables complete", ["schema.sql"]),
    }

    context, decision = TopKCommunicationRouter().route(tasks["target"], completed, tasks)

    assert tuple(context) == ("required", "security")
    assert decision.dependency_senders == ("required",)
    assert decision.selected_peer_senders == ("security",)
    assert decision.ranked_candidates[0].score > decision.ranked_candidates[1].score


def test_router_top_k_zero_delivers_only_contract_dependencies():
    dependency = SubTask("dependency", "analyst", "required input")
    peer = SubTask("peer", "reviewer", "optional advice")
    target = SubTask(
        "target",
        "developer",
        "implementation",
        depends_on=["dependency"],
        metadata={"communication_top_k": 0},
    )
    context, decision = TopKCommunicationRouter().route(
        target,
        {"dependency": _result("dependency", "done"), "peer": _result("peer", "done")},
        {item.id: item for item in (dependency, peer, target)},
    )

    assert tuple(context) == ("dependency",)
    assert decision.selected_peer_senders == ()


def test_orchestrator_delivers_routed_context_and_audits_decision():
    seen_context = {}
    routes = []

    def handler(task, context):
        seen_context[task.id] = tuple(sorted(context))
        return f"completed {task.id}"

    registry = AgentRegistry()
    for role in ("analyst", "reviewer", "architect", "developer"):
        registry.register(DeterministicAgent(role, handler))
    plan = Plan(
        "top-k demo",
        [
            SubTask("requirements", "analyst", "requirements"),
            SubTask("security", "reviewer", "security JWT", inputs=[]),
            SubTask("database", "architect", "database"),
            SubTask(
                "implementation",
                "developer",
                "implement JWT",
                depends_on=["requirements"],
                inputs=["security.md"],
                metadata={"communication_top_k": 1, "communication_topics": ["JWT"]},
            ),
        ],
    )
    # Give the security Agent a matching artifact without changing Agent.run().
    registry._agents["reviewer"].handler = lambda task, context: "security.md JWT evidence"

    report = Orchestrator(
        registry,
        communication_router=TopKCommunicationRouter(default_top_k=1),
        on_communication_event=lambda event, decision: routes.append((event, decision)),
    ).run(plan)

    assert report.status == "success"
    assert seen_context["implementation"][0] == "requirements"
    implementation_route = next(
        decision for event, decision in routes if decision.receiver_task_id == "implementation"
    )
    assert implementation_route.dependency_senders == ("requirements",)
    assert len(implementation_route.selected_peer_senders) == 1


def test_router_rejects_unbounded_top_k():
    target = SubTask(
        "target",
        "developer",
        "task",
        metadata={"communication_top_k": 99},
    )
    try:
        TopKCommunicationRouter(max_top_k=8).route(target, {}, {"target": target})
    except ValueError as exc:
        assert "between 0 and 8" in str(exc)
    else:
        raise AssertionError("unbounded Top-k must fail closed")

