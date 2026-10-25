from core.long_horizon import (
    AcceptanceContract,
    ArtifactOwnershipValidator,
    GoalCriterion,
    RuleBasedContractPlanner,
    StructuredInitialDAGGenerator,
)


def word_counter_contract():
    return AcceptanceContract(
        goal="build word counter",
        goal_summary="build tested word counter",
        criteria=[
            GoalCriterion("source", "word counter source exists", "file_exists", path="retry_demo/word_counter.py"),
            GoalCriterion("behavior", "count_text follows whitespace rules", "semantic", path="retry_demo/word_counter.py"),
            GoalCriterion("tests", "word counter tests exist", "file_exists", path="retry_demo/test_word_counter.py"),
            GoalCriterion("sample", "sample input exists", "file_exists", path="retry_demo/sample.txt"),
            GoalCriterion("readme", "documentation exists", "file_exists", path="retry_demo/README.md"),
            GoalCriterion(
                "command",
                "unittest succeeds",
                "command",
                command='python -m unittest discover -s retry_demo -p "test_*.py" -v',
            ),
        ],
    )


def test_rule_planner_builds_contract_native_dag_without_auth_template():
    contract = word_counter_contract()
    plan = RuleBasedContractPlanner().build(contract)

    ids = [task.id for task in plan.subtasks]
    descriptions = "\n".join(task.description for task in plan.subtasks)
    outputs = [output for task in plan.subtasks for output in task.metadata["expected_outputs"]]
    owners = {
        criterion: task.id
        for task in plan.subtasks
        for criterion in task.metadata["contract_criteria"]
    }

    assert "implementation_auth" not in ids
    assert "auth" not in descriptions.lower()
    assert sorted(outputs) == sorted([
        "retry_demo/word_counter.py",
        "retry_demo/test_word_counter.py",
        "retry_demo/sample.txt",
        "retry_demo/README.md",
    ])
    assert set(owners) == {item.id for item in contract.criteria}
    assert len(owners) == sum(len(task.metadata["contract_criteria"]) for task in plan.subtasks)
    ArtifactOwnershipValidator().validate(plan, contract)


class EmptyClient:
    def __init__(self):
        self.calls = 0

    def chat(self, _messages, tools=None):
        self.calls += 1
        return {"content": ""}


def test_structured_initial_planner_falls_back_to_contract_native_rules():
    client = EmptyClient()
    events = []
    plan = StructuredInitialDAGGenerator(
        client,
        on_event=lambda event, payload: events.append(event),
    ).generate(word_counter_contract())

    assert client.calls == 2
    assert "initial_plan_fallback" in events
    assert all("auth" not in task.id for task in plan.subtasks)
