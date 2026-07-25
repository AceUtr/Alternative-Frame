from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .agents import AgentRegistry
from .domains import DomainRegistry
from .long_horizon.acceptance_contract import AcceptanceContract
from .long_horizon.contract_validator import ContractValidationError, ContractValidator
from .models import Plan
from .tools.registry import ToolRegistry


@dataclass(frozen=True)
class PreflightIssue:
    code: str
    message: str
    blocking: bool = True


@dataclass
class PreflightReport:
    domain: str
    issues: list[PreflightIssue] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not any(issue.blocking for issue in self.issues)

    def require_ready(self) -> "PreflightReport":
        if not self.ready:
            detail = "; ".join(f"{item.code}: {item.message}" for item in self.issues if item.blocking)
            raise RuntimeError(f"Harness preflight failed: {detail}")
        return self


class HarnessPreflightChecker:
    """Fail before execution when a domain's declared capabilities are unavailable."""

    def __init__(self, contract_validator: ContractValidator | None = None) -> None:
        self.contract_validator = contract_validator or ContractValidator()

    def check(
        self,
        *,
        domains: DomainRegistry,
        domain: str,
        plan: Plan,
        agents: AgentRegistry,
        tools: ToolRegistry,
        workspace: str | Path,
        contract: AcceptanceContract | None = None,
        model_probe: Callable[[], object] | None = None,
    ) -> PreflightReport:
        report = PreflightReport(domain=domain)
        self._check_domain(domains, domain, report)
        self._check_plan(plan, report)
        self._check_roles(plan, agents, report)
        self._check_tools(plan, tools, report)
        self._check_workspace(Path(workspace), report)
        self._check_contract(plan, contract, report)
        self._check_model(model_probe, report)
        return report

    @staticmethod
    def _check_domain(domains: DomainRegistry, domain: str, report: PreflightReport) -> None:
        if domains.has(domain):
            report.checks.append(f"domain_registered={domain}")
        else:
            report.issues.append(PreflightIssue("domain_not_registered", domain))

    @staticmethod
    def _check_plan(plan: Plan, report: PreflightReport) -> None:
        try:
            plan.validate()
            report.checks.append(f"dag_valid=true tasks={len(plan.subtasks)}")
        except (TypeError, ValueError) as exc:
            report.issues.append(PreflightIssue("invalid_plan", str(exc)))

    @staticmethod
    def _check_roles(plan: Plan, agents: AgentRegistry, report: PreflightReport) -> None:
        required = {task.role for task in plan.subtasks}
        missing = sorted(required - set(agents.roles()))
        if missing:
            report.issues.append(PreflightIssue("missing_agent_roles", ", ".join(missing)))
        else:
            report.checks.append(f"agent_roles_available={len(required)}")

    @staticmethod
    def _check_tools(plan: Plan, tools: ToolRegistry, report: PreflightReport) -> None:
        required = {
            str(name)
            for task in plan.subtasks
            for name in task.metadata.get("required_tools", [])
            if str(name).strip()
        }
        missing = sorted(required - set(tools.names()))
        if missing:
            report.issues.append(PreflightIssue("missing_tools", ", ".join(missing)))
        else:
            report.checks.append(f"tools_available={len(required)}")

    @staticmethod
    def _check_workspace(workspace: Path, report: PreflightReport) -> None:
        try:
            workspace.mkdir(parents=True, exist_ok=True)
            probe = workspace / f".preflight-{uuid4().hex}.tmp"
            probe.write_text("ok", encoding="ascii")
            probe.unlink()
            report.checks.append(f"workspace_writable={workspace.resolve()}")
        except OSError as exc:
            report.issues.append(PreflightIssue("workspace_not_writable", str(exc)))

    def _check_contract(
        self, plan: Plan, contract: AcceptanceContract | None, report: PreflightReport
    ) -> None:
        if contract is None:
            report.issues.append(PreflightIssue("contract_missing", "an acceptance contract is required"))
            return
        try:
            self.contract_validator.validate(contract, expected_goal=plan.goal)
            report.checks.append(f"contract_valid=true criteria={len(contract.criteria)}")
        except (ContractValidationError, TypeError, ValueError) as exc:
            report.issues.append(PreflightIssue("invalid_contract", str(exc)))

    @staticmethod
    def _check_model(model_probe: Callable[[], object] | None, report: PreflightReport) -> None:
        if model_probe is None:
            report.checks.append("model_probe=skipped")
            return
        try:
            outcome = model_probe()
            ok = outcome[0] if isinstance(outcome, tuple) else bool(outcome)
            detail = outcome[1] if isinstance(outcome, tuple) and len(outcome) > 1 else ""
            if ok:
                report.checks.append("model_connection=ok")
            else:
                report.issues.append(PreflightIssue("model_connection_failed", str(detail or "probe returned false")))
        except Exception as exc:
            report.issues.append(PreflightIssue("model_connection_failed", f"{type(exc).__name__}: {exc}"))
