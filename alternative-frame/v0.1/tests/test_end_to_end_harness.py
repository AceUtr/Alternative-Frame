import json
from pathlib import Path

from core.acceptance import AcceptanceEvaluator
from core.agents import Agent, AgentResult
from core.domains import DomainAdapter, DomainRegistry
from core.local_recovery import LocalDAGRecoveryController
from core.long_horizon import AcceptanceContract, GoalCriterion, LongHorizonController, LongHorizonStore
from core.models import Plan, SubTask
from core.orchestrator import Orchestrator
from core.preflight import HarnessPreflightChecker
from core.tools import Tool, ToolResult


class ArtifactWriter(Tool):
    name = "artifact_writer"

    def __init__(self, workspace):
        self.workspace = Path(workspace)

    def schema(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                    "required": ["path", "content"],
                },
            },
        }

    def execute(self, arguments):
        relative = Path(arguments["path"])
        target = (self.workspace / relative).resolve()
        if self.workspace.resolve() not in target.parents:
            return ToolResult(self.name, False, error="path escapes workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(arguments["content"], encoding="utf-8")
        return ToolResult(
            self.name,
            True,
            output=f"wrote {relative.as_posix()}",
            metadata={"artifacts": [relative.as_posix()]},
        )


class RecoveringWriterAgent(Agent):
    role = "writer"

    def __init__(self, tools):
        self.tools = tools
        self.calls = 0

    def run(self, task, context):
        self.calls += 1
        if not task.metadata.get("local_recovery_feedback"):
            return AgentResult(task.id, "failed", failures=["intentional first-pass failure"])
        result = self.tools.execute(
            "artifact_writer", {"path": "artifacts/result.txt", "content": "recovered\n"}
        )
        return AgentResult(
            task.id,
            "success" if result.success else "failed",
            summary=result.output,
            artifacts=result.metadata.get("artifacts", []),
            tool_records=[{
                "tool": result.tool,
                "success": result.success,
                "exit_code": result.exit_code,
                "metadata": result.metadata,
            }],
            failures=[] if result.success else [result.error],
        )


class EvidenceAgent(Agent):
    role = "reviewer"

    def __init__(self, tools):
        self.tools = tools

    def run(self, task, context):
        assert context["produce"].status == "success"
        result = self.tools.execute(
            "artifact_writer", {"path": "artifacts/evidence.md", "content": "verified\n"}
        )
        return AgentResult(
            task.id,
            "success",
            summary="verified evidence",
            artifacts=result.metadata["artifacts"],
            tool_records=[{"tool": result.tool, "success": True, "metadata": result.metadata}],
        )


class E2EAdapter(DomainAdapter):
    name = "e2e"

    def register_tools(self, registry, workspace):
        registry.register(ArtifactWriter(workspace))

    def build_agents(self, model_client, tools):
        return [RecoveringWriterAgent(tools), EvidenceAgent(tools)]

    def build_plan(self, goal):
        return Plan(
            goal,
            [
                SubTask(
                    "produce",
                    "writer",
                    "produce result",
                    max_retries=0,
                    metadata={
                        "required_tools": ["artifact_writer"],
                        "expected_outputs": ["artifacts/result.txt"],
                        "checks": [{"id": "result", "check_type": "file_exists", "path": "artifacts/result.txt"}],
                    },
                ),
                SubTask(
                    "review",
                    "reviewer",
                    "record evidence",
                    depends_on=["produce"],
                    metadata={
                        "required_tools": ["artifact_writer"],
                        "expected_outputs": ["artifacts/evidence.md"],
                        "checks": [{"id": "evidence", "check_type": "file_exists", "path": "artifacts/evidence.md"}],
                    },
                ),
            ],
            final_acceptance=["result", "evidence"],
        )

    def build_contract(self, goal):
        return AcceptanceContract(
            goal=goal,
            goal_summary="Produce and independently verify a result",
            criteria=[
                GoalCriterion("result", "Result exists", "file_exists", path="artifacts/result.txt"),
                GoalCriterion("evidence", "Evidence exists", "file_exists", path="artifacts/evidence.md"),
            ],
        )

    def reset_workspace(self, workspace):
        Path(workspace).mkdir(parents=True, exist_ok=True)


def test_full_harness_preflight_local_recovery_acceptance_and_persistence(tmp_path):
    workspace = tmp_path / "workspace"
    runs = tmp_path / "runs"
    adapter = E2EAdapter()
    adapter.reset_workspace(workspace)
    domains = DomainRegistry([adapter])
    tools, agents = adapter.configure(workspace)
    plan = adapter.build_plan("deliver verified artifacts")
    contract = adapter.build_contract(plan.goal)

    preflight = HarnessPreflightChecker().check(
        domains=domains,
        domain="e2e",
        plan=plan,
        agents=agents,
        tools=tools,
        workspace=workspace,
        contract=contract,
    )
    preflight.require_ready()

    orchestrator = Orchestrator(agents, acceptance=AcceptanceEvaluator(workspace))
    local_recovery = LocalDAGRecoveryController(orchestrator, max_cycles=1)
    controller = LongHorizonController(
        orchestrator,
        initial_planner=lambda _state: plan,
        store=LongHorizonStore(runs),
        acceptance_contract=contract.to_dict(),
        local_recovery=local_recovery,
    )

    report = controller.run(plan.goal, run_id="e2e-run")

    assert report.status == "completed"
    assert report.state.phase == 1
    assert report.state.phases[0].local_recovery_cycles == 1
    assert report.state.phases[0].executed_task_count == 4
    assert (workspace / "artifacts/result.txt").read_text(encoding="utf-8") == "recovered\n"
    assert (workspace / "artifacts/evidence.md").is_file()
    persisted = json.loads((runs / "e2e-run/state.json").read_text(encoding="utf-8"))
    assert persisted["status"] == "completed"
    assert persisted["acceptance_contract"]["criteria"][0]["id"] == "result"
    events = (runs / "e2e-run/events.jsonl").read_text(encoding="utf-8")
    assert '"event": "phase_finished"' in events
    assert '"event": "run_completed"' in events
