from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.domains import DomainAdapter, DomainRegistry
from core.preflight import HarnessPreflightChecker


TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt", ".env"}
SKIP_PARTS = {".git", ".pytest_cache", ".pytest_tmp", "__pycache__", "runs", "reports"}
SECRET_PATTERNS = (
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._-]{16,}", re.IGNORECASE)),
    (
        "assigned_secret",
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|secret)\b\s*[:=]\s*[\"']"
            r"(?!your-|example|placeholder|dummy|test|\$\{|os\.getenv)[^\"']{12,}[\"']"
        ),
    ),
)
PERSONAL_PATH = re.compile(r"(?i)(?:[A-Z]:[\\/]Users[\\/][^\\/\s]+|/home/[^/\s]+)")


@dataclass
class ValidationCheck:
    name: str
    category: str
    status: str
    detail: str
    duration_seconds: float = 0.0


@dataclass
class ValidationReport:
    target: str
    manifest: str
    status: str = "failed"
    started_at: str = ""
    finished_at: str = ""
    checks: list[ValidationCheck] = field(default_factory=list)
    report_path: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ContributionValidator:
    def __init__(self, project_root: str | Path, timeout_seconds: int = 180) -> None:
        self.root = Path(project_root).resolve()
        self.timeout_seconds = timeout_seconds

    def validate(self, manifest_path: str | Path, *, run_smoke: bool = True) -> ValidationReport:
        path = Path(manifest_path).resolve()
        manifest = json.loads(path.read_text(encoding="utf-8"))
        self._validate_manifest(manifest)
        report = ValidationReport(
            target=manifest["id"],
            manifest=self._relative(path),
            started_at=self._now(),
        )

        files_ok = self._check_files(manifest, report)
        imports_ok = self._check_imports(manifest, report)
        symbols_ok = self._check_symbols(manifest, report) if imports_ok else False
        adapter_ok = self._check_adapter(manifest, report) if imports_ok else False
        scan_ok = self._scan_sources(manifest, report)
        test_prerequisites = files_ok and imports_ok and symbols_ok and adapter_ok and scan_ok
        if test_prerequisites:
            tests_ok = self._run_commands(manifest.get("test_commands", []), "tests", report)
        else:
            tests_ok = False
            report.checks.append(ValidationCheck("tests", "tests", "skipped", "structure, import, interface, preflight, or security checks failed"))

        prerequisites_ok = files_ok and imports_ok and symbols_ok and adapter_ok and scan_ok and tests_ok
        smoke = manifest.get("smoke_command")
        if not run_smoke:
            report.checks.append(ValidationCheck("smoke", "smoke", "skipped", "disabled by --skip-smoke"))
        elif not smoke:
            report.checks.append(ValidationCheck("smoke", "smoke", "skipped", "no smoke command declared"))
        elif not prerequisites_ok:
            report.checks.append(ValidationCheck("smoke", "smoke", "skipped", "prerequisite checks failed"))
        else:
            self._run_commands([smoke], "smoke", report)

        report.status = "passed" if not any(item.status == "failed" for item in report.checks) else "failed"
        report.finished_at = self._now()
        return report

    def write_report(self, report: ValidationReport, output_dir: str | Path) -> Path:
        output = Path(output_dir).resolve()
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = output / f"{report.target}-{stamp}.json"
        report.report_path = self._relative(target)
        payload = self._sanitize_value(report.to_dict())
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        latest = output / f"{report.target}-latest.json"
        latest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def _check_files(self, manifest, report) -> bool:
        missing = [item for item in manifest.get("required_files", []) if not (self.root / item).is_file()]
        status = "passed" if not missing else "failed"
        detail = f"all {len(manifest.get('required_files', []))} required files exist" if not missing else "missing: " + ", ".join(missing)
        report.checks.append(ValidationCheck("required_files", "structure", status, detail))
        return not missing

    def _check_imports(self, manifest, report) -> bool:
        ok = True
        for module in manifest.get("import_modules", []):
            started = time.perf_counter()
            try:
                importlib.invalidate_caches()
                importlib.import_module(module)
                status, detail = "passed", f"imported {module}"
            except Exception as exc:
                ok = False
                status, detail = "failed", self._redact(f"{module}: {type(exc).__name__}: {exc}")
            report.checks.append(ValidationCheck(f"import:{module}", "import", status, detail, time.perf_counter() - started))
        return ok

    def _check_symbols(self, manifest, report) -> bool:
        ok = True
        for module_name, names in manifest.get("required_symbols", {}).items():
            module = importlib.import_module(module_name)
            missing = [name for name in names if not hasattr(module, name)]
            if missing:
                ok = False
                status, detail = "failed", "missing: " + ", ".join(missing)
            else:
                status, detail = "passed", f"found {len(names)} required symbols"
            report.checks.append(ValidationCheck(f"symbols:{module_name}", "interface", status, detail))
        return ok

    def _check_adapter(self, manifest, report) -> bool:
        spec = manifest.get("adapter")
        if not spec:
            report.checks.append(ValidationCheck("domain_adapter", "interface", "skipped", "not required for this contribution"))
            return True
        started = time.perf_counter()
        try:
            module = importlib.import_module(spec["module"])
            adapter_type = getattr(module, spec["class"])
            if not isinstance(adapter_type, type) or not issubclass(adapter_type, DomainAdapter):
                raise TypeError(f"{spec['class']} must subclass DomainAdapter")
            adapter = adapter_type()
            workspace = self.root / ".validation_tmp" / manifest["id"] / "workspace"
            adapter.reset_workspace(workspace)
            tools, agents = adapter.configure(workspace, model_client=None)
            goal = manifest.get("validation_goal", f"validate {manifest['id']} contribution")
            plan = adapter.build_plan(goal)
            contract = adapter.build_contract(goal)
            domains = DomainRegistry([adapter])
            preflight = HarnessPreflightChecker().check(
                domains=domains,
                domain=adapter.name,
                plan=plan,
                agents=agents,
                tools=tools,
                workspace=workspace,
                contract=contract,
            )
            preflight.require_ready()
            detail = f"adapter={adapter.name}; roles={len(agents.roles())}; tools={len(tools.names())}; tasks={len(plan.subtasks)}"
            status, ok = "passed", True
        except Exception as exc:
            detail = self._redact(f"{type(exc).__name__}: {exc}")
            status, ok = "failed", False
        report.checks.append(ValidationCheck("domain_adapter_preflight", "preflight", status, detail, time.perf_counter() - started))
        return ok

    def _scan_sources(self, manifest, report) -> bool:
        findings = []
        for relative in manifest.get("scan_paths", []):
            path = (self.root / relative).resolve()
            candidates = [path] if path.is_file() else path.rglob("*") if path.is_dir() else []
            for candidate in candidates:
                if not candidate.is_file() or candidate.suffix.lower() not in TEXT_SUFFIXES:
                    continue
                if any(part in SKIP_PARTS for part in candidate.parts):
                    continue
                try:
                    text = candidate.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                rel = candidate.relative_to(self.root).as_posix()
                for label, pattern in SECRET_PATTERNS:
                    if pattern.search(text):
                        findings.append(f"{rel}: {label}")
                if PERSONAL_PATH.search(text):
                    findings.append(f"{rel}: personal_absolute_path")
        status = "passed" if not findings else "failed"
        detail = "no credential or personal-path patterns found" if not findings else "; ".join(sorted(set(findings)))
        report.checks.append(ValidationCheck("sensitive_data_scan", "security", status, detail))
        return not findings

    def _run_commands(self, commands, category, report) -> bool:
        ok = True
        for index, command in enumerate(commands, start=1):
            if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
                report.checks.append(ValidationCheck(f"{category}:{index}", category, "failed", "command must be a non-empty string array"))
                ok = False
                continue
            started = time.perf_counter()
            env = dict(os.environ)
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.root,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    env=env,
                    shell=False,
                )
                output = self._compact((completed.stdout or "") + "\n" + (completed.stderr or ""))
                status = "passed" if completed.returncode == 0 else "failed"
                detail = f"exit_code={completed.returncode}; command={' '.join(command)}; output={output}"
                ok = ok and completed.returncode == 0
            except subprocess.TimeoutExpired:
                status, detail, ok = "failed", f"timeout after {self.timeout_seconds}s; command={' '.join(command)}", False
            except OSError as exc:
                status, detail, ok = "failed", f"{type(exc).__name__}: {exc}", False
            report.checks.append(ValidationCheck(f"{category}:{index}", category, status, detail, time.perf_counter() - started))
        return ok

    @staticmethod
    def _validate_manifest(manifest):
        if not isinstance(manifest, dict) or not isinstance(manifest.get("id"), str):
            raise ValueError("manifest must contain a string id")
        for key in ("required_files", "import_modules", "test_commands", "scan_paths"):
            if key in manifest and not isinstance(manifest[key], list):
                raise ValueError(f"manifest {key} must be a list")

    @staticmethod
    def _compact(value: str, limit: int = 1200) -> str:
        text = " ".join(ContributionValidator._redact(value).split())
        return text if len(text) <= limit else text[: limit - 3] + "..."

    @staticmethod
    def _redact(value: str) -> str:
        text = str(value)
        for _label, pattern in SECRET_PATTERNS:
            text = pattern.sub("[REDACTED]", text)
        return PERSONAL_PATH.sub("[PERSONAL_PATH]", text)

    @classmethod
    def _sanitize_value(cls, value):
        if isinstance(value, dict):
            return {key: cls._sanitize_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._sanitize_value(item) for item in value]
        if isinstance(value, str):
            return cls._redact(value)
        return value

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return path.name

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
