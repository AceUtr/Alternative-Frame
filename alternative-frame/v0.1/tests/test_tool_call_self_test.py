import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from core.models import SubTask
from core.tool_calling_agent import ToolCallingAgent
from core.tools import FileEditor, ToolRegistry
from ui import build_tool_test_plan, prepare_repair_fixture


class FakeToolCallingClient:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "file_editor",
                            "arguments": '{"action":"write","path":"hello.py","content":"def add(a, b):\\n    return a + b\\n"}',
                        },
                    }
                ],
            }
        return {"content": "Created hello.py", "tool_calls": []}


def test_tool_test_plan_bypasses_software_template():
    plan = build_tool_test_plan("create and test hello.py")
    assert [task.id for task in plan.subtasks] == ["tool_call_self_test"]
    assert plan.subtasks[0].role == "developer"
    assert plan.subtasks[0].max_retries == 0


def test_tool_agent_writes_inside_workspace_and_emits_events(tmp_path):
    events = []
    agent = ToolCallingAgent(
        "developer",
        FakeToolCallingClient(),
        ToolRegistry([FileEditor(tmp_path)]),
        "Use tools.",
        on_tool_event=lambda event, payload: events.append((event, payload)),
    )

    result = agent.run(SubTask("self-test", "developer", "create hello.py"), {})

    assert result.status == "success"
    assert (tmp_path / "hello.py").read_text(encoding="utf-8").endswith("return a + b\n")
    assert [event for event, _ in events] == ["tool_started", "tool_finished"]
    assert events[-1][1]["success"] is True


def test_file_editor_rejects_workspace_escape(tmp_path):
    result = ToolRegistry([FileEditor(tmp_path)]).execute(
        "file_editor",
        {"action": "write", "path": "../outside.py", "content": "bad"},
    )
    assert result.success is False
    assert "escapes workspace" in result.error


def test_repair_fixture_is_reset_to_a_known_failure(tmp_path):
    prepare_repair_fixture(tmp_path)

    namespace = {}
    exec((tmp_path / "hello.py").read_text(encoding="utf-8"), namespace)
    assert namespace["add"](2, 3) == -1
