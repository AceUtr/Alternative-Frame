from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Dict, Mapping

from .models import AgentResult, SubTask, utc_now



class Agent(ABC):
    """Minimal role-based agent contract used by orchestrator."""

    role: str


    @abstractmethod
    def run(
        self,
        task: SubTask,
        context: Mapping[str, AgentResult]
    ) -> AgentResult:

        raise NotImplementedError





class AgentRegistry:


    def __init__(self):

        self._agents: Dict[str, Agent] = {}



    def register(self, agent: Agent):

        if not getattr(agent,"role",None):

            raise ValueError(
                "Agent must define a role"
            )

        self._agents[agent.role]=agent




    def get(self,role:str):

        if role not in self._agents:

            raise KeyError(
                f"No agent registered for role: {role}"
            )

        return self._agents[role]




    def roles(self):

        return tuple(sorted(self._agents))



    def has(self,role:str):

        return role in self._agents







@dataclass
class DeterministicAgent(Agent):

    role:str

    handler:Callable | None=None




    def run(
        self,
        task:SubTask,
        context:Mapping[str,AgentResult]
    ) -> AgentResult:


        started = utc_now()


        try:


            result = self.handler(
                task,
                context
            ) if self.handler else None



            # ==================================
            # 关键修复
            # handler 已经返回 AgentResult
            # 直接返回
            # ==================================

            if isinstance(result,AgentResult):


                result.started_at = started

                result.finished_at = utc_now()

                return result





            # ==================================
            # 兼容旧模式
            # handler 返回字符串
            # ==================================

            return AgentResult(

                subtask_id=task.id,

                status="success",

                summary=result or
                f"{self.role} completed: {task.description}",


                artifacts=[
                    f"artifact://{task.id}"
                ],


                evidence=[
                    f"role={self.role}",
                    f"acceptance_checks={len(task.acceptance)}"
                ],


                started_at=started,

                finished_at=utc_now()

            )




        except Exception as exc:


            return AgentResult(

                subtask_id=task.id,

                status="failed",

                summary=f"{self.role} failed",

                failures=[
                    str(exc)
                ],

                started_at=started,

                finished_at=utc_now()

            )
