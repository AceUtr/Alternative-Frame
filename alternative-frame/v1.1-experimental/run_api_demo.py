"""Run the same research/software plans with a user-selected shared model.

This is opt-in because it requires an API key:
    $env:MODEL_BASE_URL = "https://api.openai.com/v1"
    $env:MODEL_API_KEY = "..."
    $env:MODEL_NAME = "..."
    python run_api_demo.py
"""

from core.agents import AgentRegistry
from core.llm_agent import ConfiguredModelAgent
from core.main_agent import MainAgent
from core.model_client import ModelConfig, OpenAICompatibleClient
from core.orchestrator import Orchestrator
from core.planning import PlanningPipeline


ROLE_PROMPTS = {
    "researcher": "You are a research analyst. Produce evidence-backed, concise work for the assigned subtask.",
    "experimenter": "You are an experiment engineer. Design reproducible experiments and report measurable evidence.",
    "reviewer": "You are an independent reviewer. Check the acceptance criteria and clearly report risks and evidence.",
    "analyst": "You are a requirements analyst. Turn the assigned requirement work into precise, testable statements.",
    "architect": "You are a software architect. Produce a simple, implementable design with explicit interfaces.",
    "developer": "You are a software developer. Explain the implementation needed for the assigned task and its tests.",
    "tester": "You are a test engineer. Design tests that directly cover the acceptance criteria.",
}


def build_api_runtime() -> MainAgent:
    config = ModelConfig.from_env()
    client = OpenAICompatibleClient(config)
    registry = AgentRegistry()
    for role, prompt in ROLE_PROMPTS.items():
        registry.register(ConfiguredModelAgent(role, client, prompt))
    return MainAgent(Orchestrator(registry, max_workers=4), PlanningPipeline().build)


if __name__ == "__main__":
    runtime = build_api_runtime()
    goal = input("输入任务目标（例如：开发一个 FastAPI 服务，需要测试和文档）：").strip()
    report = runtime.execute(goal)
    print(f"status={report.status} rounds={report.rounds}")
    for task_id, result in report.results.items():
        print(f"{task_id}: {result.status} | {result.summary[:160]}")

