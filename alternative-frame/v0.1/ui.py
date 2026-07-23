"""Fresh interactive UI v0.1 with user-selectable model API."""

from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict

from core.agents import AgentRegistry, DeterministicAgent
from core.acceptance import AcceptanceEvaluator
from core.long_horizon import (
    AcceptanceContract,
    RuleBasedContractPlanner,
    ContractValidator,
    LongHorizonController,
    LongHorizonStore,
    ReportStatusEvaluator,
    StructuredGlobalEvaluator,
    DeterministicGlobalEvaluator,
    StructuredGoalContractGenerator,
    StructuredInitialDAGGenerator,
    StructuredReplanner,
    ResilientReplanner,
    DeterministicRecoveryPlanner,
)
from core.tool_calling_agent import ToolCallingAgent
from core.main_agent import MainAgent
from core.model_client import ModelConfig, OpenAICompatibleClient
from core.models import Plan, SubTask
from core.orchestrator import Orchestrator, RunReport
from core.planning import PlanningPipeline
from core.tools import ExperimentRunner, FileEditor, GitClient, ShellRunner, TestRunner, ToolRegistry
from run_api_demo import ROLE_PROMPTS


COLORS = {
    "bg": "#F4FAF8",
    "card": "#FFFFFF",
    "mint": "#DDF4EC",
    "mint_dark": "#2E7D68",
    "blue": "#E7F0FF",
    "blue_dark": "#315F96",
    "text": "#24332F",
    "muted": "#71817B",
    "line": "#DCE9E4",
    "success": "#2F8F6B",
    "danger": "#B85C5C",
}


PROJECT_DIR = Path(__file__).resolve().parent
TOOL_TEST_WORKSPACE = PROJECT_DIR / "tool_test_workspace"
DEFAULT_EXECUTION_MODES = ("标准多 Agent", "长程任务")
DEVELOPER_EXECUTION_MODES = ("工具调用自检", "失败修复自检")


def long_horizon_runs_root() -> Path:
    return Path(os.getenv("LONG_HORIZON_RUNS_DIR", str(PROJECT_DIR / "runs" / "long_horizon")))


def build_registry(client=None, workspace=None, on_tool_event=None, tool_test: bool = False) -> AgentRegistry:
    registry = AgentRegistry()
    if client is not None:
        workspace = workspace or __import__("pathlib").Path.cwd()
        shell = ShellRunner(workspace)
        file_editor = FileEditor(workspace)
        git = GitClient(workspace)
        tests = TestRunner(shell)
        experiment = ExperimentRunner(shell)
        permissions = {
            "researcher": [file_editor, experiment],
            "experimenter": [file_editor, experiment, shell],
            "reviewer": [file_editor, tests, git],
            "analyst": [file_editor],
            "architect": [file_editor],
            "developer": [file_editor, shell, git, tests],
            "tester": [file_editor, shell, tests],
        }
    for role, prompt in ROLE_PROMPTS.items():
        if client is None:
            registry.register(DeterministicAgent(role))
        else:
            max_steps = 24 if role in ("developer", "experimenter") else 12
            if tool_test:
                prompt += (
                    "\nThis is an isolated tool-call self-test. Perform the requested workspace actions "
                    "with tools, run the real unittest command, and stop immediately after it passes."
                )
            registry.register(
                ToolCallingAgent(
                    role,
                    client,
                    ToolRegistry(permissions[role]),
                    prompt,
                    max_steps=max_steps,
                    on_tool_event=on_tool_event,
                )
            )
    return registry


def build_tool_test_plan(goal: str) -> Plan:
    return Plan(
        goal=goal,
        subtasks=[
            SubTask(
                id="tool_call_self_test",
                role="developer",
                description=goal,
                acceptance=["files_created", "tests_pass"],
                max_retries=0,
                metadata={
                    "expected_outputs": ["hello.py", "test_hello.py"],
                    "checks": [
                        {"id": "files_created", "check_type": "file_exists"},
                        {
                            "id": "tests_pass",
                            "check_type": "command",
                            "command": "python -m unittest -v test_hello.py",
                        },
                    ],
                },
            )
        ],
        final_acceptance=["files_created", "tests_pass"],
    )


def prepare_repair_fixture(workspace: Path = TOOL_TEST_WORKSPACE) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "hello.py").write_text(
        'def add(a, b):\n'
        '    """Return the sum of two values."""\n'
        '    # Deliberate demo defect: diagnose this from the failing test.\n'
        '    return a - b\n',
        encoding="utf-8",
    )


def build_recovery_plan(pipeline: PlanningPipeline, state, evaluation) -> Plan:
    plan = pipeline.build(state.goal)
    failure_context = "; ".join(evaluation.failures) or "no structured failure code"
    recovery_note = (
        f"\nRecovery phase {state.phase + 1}. Previous global evaluation: {evaluation.reason}. "
        f"Failures: {failure_context}. Inspect existing artifacts and change strategy before retrying."
    )
    for task in plan.subtasks:
        task.description += recovery_note
    return plan


def validate_contract_json(text: str, expected_goal: str, validator=None) -> AcceptanceContract:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("验收合同必须是 JSON 对象")
    contract = AcceptanceContract.from_dict(payload)
    (validator or ContractValidator()).validate(contract, expected_goal=expected_goal)
    return contract


class ContractJsonEditor(tk.Toplevel):
    def __init__(self, parent, contract, on_apply):
        super().__init__(parent)
        self.title("编辑验收合同 JSON")
        self.geometry("760x620")
        self.minsize(620, 480)
        self.transient(parent)
        self.configure(bg=COLORS["bg"])
        self.contract = contract
        self.on_apply = on_apply
        self.protocol("WM_DELETE_WINDOW", self._close)

        body = tk.Frame(self, bg=COLORS["bg"], padx=16, pady=14)
        body.pack(fill=tk.BOTH, expand=True)
        tk.Label(
            body,
            text="修改后必须重新通过安全校验；原始目标、路径和命令均不可绕过约束。",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=tk.W, pady=(0, 8))
        self.editor = tk.Text(
            body,
            wrap=tk.NONE,
            font=("Cascadia Mono", 9),
            background="#F8FBFA",
            foreground=COLORS["text"],
            insertbackground=COLORS["mint_dark"],
            highlightbackground=COLORS["line"],
            highlightthickness=1,
            padx=10,
            pady=10,
        )
        self.editor.pack(fill=tk.BOTH, expand=True)
        self.editor.insert("1.0", json.dumps(contract.to_dict(), ensure_ascii=False, indent=2))

        buttons = tk.Frame(body, bg=COLORS["bg"])
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="取消", style="Soft.TButton", command=self._close).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="校验并应用修改", style="Accent.TButton", command=self._apply).pack(side=tk.RIGHT, padx=(0, 8))
        self.grab_set()

    def _apply(self):
        try:
            contract = validate_contract_json(
                self.editor.get("1.0", tk.END),
                expected_goal=self.contract.goal,
            )
        except Exception as exc:
            messagebox.showerror("合同校验失败", str(exc), parent=self)
            return
        self.on_apply(contract)
        self._close()

    def _close(self):
        parent = self.master
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        if parent.winfo_exists():
            parent.grab_set()
            parent.focus_set()


class ContractPreviewDialog(tk.Toplevel):
    def __init__(self, parent, contract, reply_queue):
        super().__init__(parent)
        self.title("确认最终验收合同")
        window_height = max(460, min(650, self.winfo_screenheight() - 140))
        self.geometry(f"900x{window_height}")
        self.minsize(700, 420)
        self.transient(parent)
        self.configure(bg=COLORS["bg"])
        self.contract = contract
        self.original_goal = contract.goal
        self.reply_queue = reply_queue
        self.resolved = False
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Control-Return>", lambda _event: self._confirm())

        root = tk.Frame(self, bg=COLORS["bg"], padx=18, pady=16)
        root.pack(fill=tk.BOTH, expand=True)
        ttk.Label(root, text="执行前确认最终验收合同", style="Hero.TLabel").pack(anchor=tk.W)
        tk.Label(
            root,
            text="确认前不会启动任何子 Agent 或工作区工具。请重点检查产物路径、测试命令和安全要求。",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=tk.W, pady=(2, 10))

        summary_card = tk.Frame(root, bg=COLORS["card"], highlightbackground=COLORS["line"], highlightthickness=1, padx=12, pady=10)
        summary_card.pack(fill=tk.X)
        tk.Label(summary_card, text="目标摘要", bg=COLORS["card"], fg=COLORS["mint_dark"], font=("Microsoft YaHei UI", 10, "bold")).pack(anchor=tk.W)
        self.summary = tk.Label(summary_card, bg=COLORS["card"], fg=COLORS["text"], justify=tk.LEFT, wraplength=820, font=("Microsoft YaHei UI", 10))
        self.summary.pack(anchor=tk.W, pady=(4, 0))

        # Pack the action area before the expandable table so Windows DPI
        # scaling can never push the confirmation button below the viewport.
        buttons = tk.Frame(root, bg=COLORS["bg"])
        buttons.pack(side=tk.BOTTOM, fill=tk.X, pady=(12, 0))
        ttk.Button(buttons, text="取消任务", style="Soft.TButton", command=self._cancel).pack(side=tk.LEFT)
        ttk.Button(buttons, text="编辑 JSON", style="Soft.TButton", command=self._edit).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="确认并开始执行", style="Accent.TButton", command=self._confirm).pack(side=tk.RIGHT)
        tk.Label(
            buttons,
            text="快捷键：Ctrl+Enter 确认",
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=("Microsoft YaHei UI", 8),
        ).pack(side=tk.RIGHT, padx=(0, 12))

        self.constraints = tk.Label(root, bg=COLORS["bg"], fg=COLORS["muted"], justify=tk.LEFT, wraplength=840, font=("Microsoft YaHei UI", 9))
        self.constraints.pack(side=tk.BOTTOM, anchor=tk.W, fill=tk.X, pady=(8, 0))

        table_card = tk.Frame(root, bg=COLORS["card"], highlightbackground=COLORS["line"], highlightthickness=1, padx=10, pady=10)
        table_card.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        columns = ("id", "required", "type", "description", "verification")
        self.criteria_tree = ttk.Treeview(table_card, columns=columns, show="headings", height=12)
        for key, title, width in [
            ("id", "标准 ID", 125),
            ("required", "必需", 55),
            ("type", "检查类型", 90),
            ("description", "完成要求", 300),
            ("verification", "路径 / 命令 / 指标", 210),
        ]:
            self.criteria_tree.heading(key, text=title)
            self.criteria_tree.column(key, width=width, anchor=tk.W)
        scrollbar = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.criteria_tree.yview)
        self.criteria_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.criteria_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._refresh()
        self.grab_set()
        self.focus_set()

    def _refresh(self):
        self.summary.configure(text=self.contract.goal_summary or self.contract.goal)
        for item in self.criteria_tree.get_children():
            self.criteria_tree.delete(item)
        for criterion in self.contract.criteria:
            verification = criterion.path or criterion.command or (
                f"{criterion.metric_name} >= {criterion.threshold}"
                if criterion.metric_name and criterion.threshold is not None
                else "语义/人工证据"
            )
            self.criteria_tree.insert(
                "",
                tk.END,
                values=(
                    criterion.id,
                    "是" if criterion.required else "否",
                    criterion.check_type,
                    criterion.description,
                    verification,
                ),
            )
        constraints = "；".join(self.contract.constraints) if self.contract.constraints else "无额外约束"
        self.constraints.configure(text=f"约束：{constraints}")

    def _edit(self):
        ContractJsonEditor(self, self.contract, self._apply_edit)

    def _apply_edit(self, contract):
        self.contract = contract
        self._refresh()

    def _confirm(self):
        try:
            ContractValidator().validate(self.contract, expected_goal=self.original_goal)
        except Exception as exc:
            messagebox.showerror("合同校验失败", str(exc), parent=self)
            return
        self._resolve(self.contract)

    def _cancel(self):
        self._resolve(None)

    def _resolve(self, value):
        if self.resolved:
            return
        self.resolved = True
        self.reply_queue.put(value)
        self.grab_release()
        self.destroy()


class RunHistoryDialog(tk.Toplevel):
    def __init__(self, parent, store, on_resume):
        super().__init__(parent)
        self.title("长程任务运行历史")
        self.geometry("840x480")
        self.minsize(680, 380)
        self.transient(parent)
        self.configure(bg=COLORS["bg"])
        self.on_resume = on_resume
        self.states = {state.run_id: state for state in store.list_runs()}

        root = tk.Frame(self, bg=COLORS["bg"], padx=18, pady=16)
        root.pack(fill=tk.BOTH, expand=True)
        ttk.Label(root, text="长程任务运行历史", style="Hero.TLabel").pack(anchor=tk.W)
        tk.Label(
            root,
            text="暂停、运行中断或失败的任务可以从持久化阶段状态继续；已完成任务仅供查看。",
            bg=COLORS["bg"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9),
        ).pack(anchor=tk.W, pady=(2, 10))
        columns = ("run_id", "status", "phase", "tasks", "updated", "goal")
        self.tree = ttk.Treeview(root, columns=columns, show="headings", height=11)
        for key, title, width in [
            ("run_id", "运行 ID", 105), ("status", "状态", 85), ("phase", "阶段", 55),
            ("tasks", "任务数", 55), ("updated", "更新时间", 145), ("goal", "目标", 300),
        ]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)
        for state in self.states.values():
            self.tree.insert("", tk.END, iid=state.run_id, values=(
                state.run_id, state.status, state.phase, state.total_tasks,
                state.updated_at.replace("T", " ")[:19], state.goal,
            ))
        self.tree.bind("<Double-1>", lambda _event: self._resume())
        buttons = tk.Frame(root, bg=COLORS["bg"])
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="关闭", style="Soft.TButton", command=self.destroy).pack(side=tk.LEFT)
        self.resume_btn = ttk.Button(buttons, text="恢复所选任务", style="Accent.TButton", command=self._resume)
        self.resume_btn.pack(side=tk.RIGHT)
        if not self.states:
            self.resume_btn.configure(state=tk.DISABLED)

    def _resume(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("请选择运行", "请先选择一条历史运行记录。", parent=self)
            return
        state = self.states[selected[0]]
        self.destroy()
        self.on_resume(state)


class FreshUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Alternative Frame · v0.1")
        self.geometry("1180x790")
        self.minsize(980, 680)
        self.configure(bg=COLORS["bg"])
        self.events = queue.Queue()
        self.running = False
        self.active_controller = None
        self.task_items: Dict[str, str] = {}
        self._style()
        self._layout()
        self.after(100, self._drain)

    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TFrame", background=COLORS["bg"])
        s.configure("Card.TFrame", background=COLORS["card"], relief="flat")
        s.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        s.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        s.configure("Hero.TLabel", background=COLORS["bg"], foreground=COLORS["mint_dark"], font=("Microsoft YaHei UI", 22, "bold"))
        s.configure("Subtitle.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Microsoft YaHei UI", 10))
        s.configure("CardTitle.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold"))
        s.configure("Accent.TButton", background=COLORS["mint_dark"], foreground="white", padding=(16, 9), font=("Microsoft YaHei UI", 10, "bold"))
        s.map("Accent.TButton", background=[("active", "#266A59"), ("disabled", "#A8C5BC")])
        s.configure("Soft.TButton", background=COLORS["mint"], foreground=COLORS["mint_dark"], padding=(12, 7))
        s.map("Soft.TButton", background=[("active", "#C9EADD")])
        s.configure("Treeview", background="white", fieldbackground="white", foreground=COLORS["text"], rowheight=30, borderwidth=0)
        s.configure("Treeview.Heading", background=COLORS["mint"], foreground=COLORS["mint_dark"], font=("Microsoft YaHei UI", 9, "bold"), relief="flat")
        s.map("Treeview", background=[("selected", "#DCEFE9")], foreground=[("selected", COLORS["text"])])
        s.configure("TEntry", padding=6)
        s.configure("TCombobox", padding=5)

    def _card(self, parent, **pack):
        outer = tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["line"], highlightthickness=1, bd=0)
        outer.pack(**pack)
        return outer

    def _layout(self):
        root = tk.Frame(self, bg=COLORS["bg"], padx=22, pady=18)
        root.pack(fill=tk.BOTH, expand=True)

        header = tk.Frame(root, bg=COLORS["bg"])
        header.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(header, text="Alternative Frame", style="Hero.TLabel").pack(anchor=tk.W)
        ttk.Label(header, text="用你选择的模型，驱动主 Agent 与多角色子 Agent 协作", style="Subtitle.TLabel").pack(anchor=tk.W, pady=(2, 0))

        top = tk.Frame(root, bg=COLORS["bg"])
        top.pack(fill=tk.X)
        left = self._card(top, side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        right = self._card(top, side=tk.LEFT, fill=tk.Y, padx=(8, 0))
        self._task_card(left)
        self._model_card(right)

        lower = tk.Frame(root, bg=COLORS["bg"])
        lower.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
        dag_card = self._card(lower, side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        log_card = self._card(lower, side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0))
        self._dag_card(dag_card)
        self._log_card(log_card)

        footer = tk.Frame(root, bg=COLORS["bg"])
        footer.pack(fill=tk.X, pady=(10, 0))
        self.status_dot = tk.Label(footer, text="●", bg=COLORS["bg"], fg=COLORS["success"], font=("Segoe UI", 10))
        self.status_dot.pack(side=tk.LEFT)
        self.status = tk.StringVar(value="就绪")
        ttk.Label(footer, textvariable=self.status, style="Subtitle.TLabel").pack(side=tk.LEFT, padx=(5, 0))

    def _task_card(self, card):
        inner = tk.Frame(card, bg=COLORS["card"], padx=16, pady=14)
        inner.pack(fill=tk.BOTH, expand=True)
        ttk.Label(inner, text="01  任务目标", style="CardTitle.TLabel").pack(anchor=tk.W)
        tk.Label(inner, text="描述你希望 Agent 团队完成的工作", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, pady=(2, 8))
        self.goal = tk.Text(inner, height=6, wrap=tk.WORD, bd=0, padx=10, pady=9, background="#F8FBFA", foreground=COLORS["text"], insertbackground=COLORS["mint_dark"], highlightbackground=COLORS["line"], highlightthickness=1, font=("Microsoft YaHei UI", 10))
        self.goal.pack(fill=tk.BOTH, expand=True)
        self.goal.insert("1.0", "开发一个 FastAPI 服务，需要用户登录、自动化测试和 API 文档")
        actions = tk.Frame(inner, bg=COLORS["card"])
        actions.pack(fill=tk.X, pady=(10, 0))
        self.execution_mode = tk.StringVar(value="标准多 Agent")
        self.execution_mode_box = ttk.Combobox(
            actions,
            textvariable=self.execution_mode,
            state="readonly",
            values=DEFAULT_EXECUTION_MODES,
            width=16,
        )
        self.execution_mode_box.pack(side=tk.LEFT)
        self.execution_mode_box.bind("<<ComboboxSelected>>", self._on_execution_mode_changed)
        self.developer_mode = tk.BooleanVar(value=False)
        tk.Checkbutton(
            actions,
            text="开发者模式",
            variable=self.developer_mode,
            command=self._toggle_developer_modes,
            bg=COLORS["card"],
            fg=COLORS["muted"],
            activebackground=COLORS["card"],
            selectcolor=COLORS["card"],
            font=("Microsoft YaHei UI", 9),
        ).pack(side=tk.LEFT, padx=(10, 0))
        self.run_btn = ttk.Button(actions, text="开始协作  →", style="Accent.TButton", command=self.start_run)
        self.run_btn.pack(side=tk.RIGHT)
        self.pause_btn = ttk.Button(actions, text="暂停", style="Soft.TButton", command=self.pause_run, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(actions, text="运行历史", style="Soft.TButton", command=self.show_run_history).pack(side=tk.RIGHT, padx=(0, 8))

    def _toggle_developer_modes(self):
        values = DEFAULT_EXECUTION_MODES + DEVELOPER_EXECUTION_MODES if self.developer_mode.get() else DEFAULT_EXECUTION_MODES
        self.execution_mode_box.configure(values=values)
        if self.execution_mode.get() not in values:
            self.execution_mode.set(DEFAULT_EXECUTION_MODES[0])

    def _on_execution_mode_changed(self, _event=None):
        mode = self.execution_mode.get()
        if mode not in ("工具调用自检", "失败修复自检"):
            return
        prompt_name = "REPAIR_PROMPT.txt" if mode == "失败修复自检" else "TEST_PROMPT.txt"
        prompt_path = TOOL_TEST_WORKSPACE / prompt_name
        if prompt_path.exists():
            prompt = prompt_path.read_text(encoding="utf-8")
        else:
            prompt = "Read requirements.txt, create hello.py and test_hello.py, then run unittest until it passes."
        self.goal.delete("1.0", tk.END)
        self.goal.insert("1.0", prompt)
        self.temperature.set("0.1")

    def _model_card(self, card):
        inner = tk.Frame(card, bg=COLORS["card"], padx=16, pady=14, width=390)
        inner.pack(fill=tk.BOTH)
        inner.pack_propagate(False)
        ttk.Label(inner, text="02  模型配置", style="CardTitle.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W)
        tk.Label(inner, text="API Key 仅保存在当前窗口内存中", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(2, 8))
        self.mode = tk.StringVar(value="本地 Stub")
        self._field(inner, 2, "运行模式", ttk.Combobox(inner, textvariable=self.mode, state="readonly", values=["本地 Stub", "API 模型"], width=25))
        self.base_url = tk.StringVar(value="https://api.openai.com/v1")
        self._field(inner, 3, "Base URL", ttk.Entry(inner, textvariable=self.base_url, width=29))
        self.api_key = tk.StringVar()
        self._field(inner, 4, "API Key", ttk.Entry(inner, textvariable=self.api_key, show="●", width=29))
        self.model_name = tk.StringVar()
        self._field(inner, 5, "模型名称", ttk.Entry(inner, textvariable=self.model_name, width=29))
        self.temperature = tk.StringVar(value="0.2")
        self.max_tokens = tk.StringVar(value="4096")
        row = tk.Frame(inner, bg=COLORS["card"])
        row.grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=5)
        tk.Label(row, text="Temperature", width=12, anchor=tk.W, bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.temperature, width=7).pack(side=tk.LEFT)
        tk.Label(row, text="Max Tokens", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=(14, 6))
        ttk.Entry(row, textvariable=self.max_tokens, width=8).pack(side=tk.LEFT)
        runtime_row = tk.Frame(inner, bg=COLORS["card"])
        runtime_row.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=5)
        self.api_timeout = tk.StringVar(value="120")
        self.replan_attempts = tk.StringVar(value="2")
        tk.Label(runtime_row, text="API Timeout", width=12, anchor=tk.W, bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT)
        ttk.Entry(runtime_row, textvariable=self.api_timeout, width=7).pack(side=tk.LEFT)
        tk.Label(runtime_row, text="Replan Attempts", bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side=tk.LEFT, padx=(14, 6))
        ttk.Entry(runtime_row, textvariable=self.replan_attempts, width=8).pack(side=tk.LEFT)
        self.test_btn = ttk.Button(inner, text="测试连接", style="Soft.TButton", command=self.test_connection)
        self.test_btn.grid(row=8, column=1, sticky=tk.E, pady=(9, 0))
        inner.columnconfigure(1, weight=1)

    def _field(self, parent, row, label, widget):
        tk.Label(parent, text=label, bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=5)
        widget.grid(row=row, column=1, sticky=tk.EW, pady=5)

    def _dag_card(self, card):
        inner = tk.Frame(card, bg=COLORS["card"], padx=14, pady=12)
        inner.pack(fill=tk.BOTH, expand=True)
        ttk.Label(inner, text="03  子任务与角色", style="CardTitle.TLabel").pack(anchor=tk.W, pady=(0, 8))
        cols = ("task", "role", "depends", "status", "attempts")
        self.tree = ttk.Treeview(inner, columns=cols, show="headings", height=11)
        for key, title, width in [("task", "子任务", 130), ("role", "角色", 120), ("depends", "依赖", 140), ("status", "状态", 90), ("attempts", "尝试", 60)]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)

    def _log_card(self, card):
        inner = tk.Frame(card, bg=COLORS["card"], padx=14, pady=12)
        inner.pack(fill=tk.BOTH, expand=True)
        head = tk.Frame(inner, bg=COLORS["card"])
        head.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(head, text="04  协作日志", style="CardTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(head, text="清空", style="Soft.TButton", command=self.clear_log).pack(side=tk.RIGHT)
        self.log = tk.Text(inner, height=11, wrap=tk.WORD, bd=0, padx=10, pady=8, state=tk.DISABLED, background="#F8FBFA", foreground=COLORS["text"], font=("Cascadia Mono", 9), highlightbackground=COLORS["line"], highlightthickness=1)
        self.log.pack(fill=tk.BOTH, expand=True)

    def _config(self):
        if self.mode.get() == "本地 Stub":
            return None
        if not self.api_key.get().strip() or not self.model_name.get().strip():
            raise ValueError("API 模式需要填写 API Key 和模型名称")
        timeout_seconds = int(self.api_timeout.get())
        replan_attempts = int(self.replan_attempts.get())
        if timeout_seconds < 10 or timeout_seconds > 600:
            raise ValueError("API Timeout 必须在 10 到 600 秒之间")
        if replan_attempts < 1 or replan_attempts > 5:
            raise ValueError("Replan Attempts 必须在 1 到 5 之间")
        return ModelConfig(
            base_url=self.base_url.get().strip().rstrip("/"),
            api_key=self.api_key.get().strip(),
            model=self.model_name.get().strip(),
            temperature=float(self.temperature.get()),
            max_tokens=int(self.max_tokens.get()),
            timeout_seconds=timeout_seconds,
        )

    def test_connection(self):
        try:
            config = self._config()
        except Exception as exc:
            messagebox.showwarning("配置不完整", str(exc))
            return
        if config is None:
            messagebox.showinfo("本地模式", "本地 Stub 不需要 API 连接。")
            return
        self.test_btn.configure(state=tk.DISABLED)
        self.status.set("正在测试模型连接...")
        threading.Thread(target=self._test_worker, args=(config,), daemon=True).start()

    def _test_worker(self, config):
        try:
            client = OpenAICompatibleClient(config)
            msg = client.chat([{"role": "user", "content": "Reply with OK only."}])
            self.events.put(("connection", msg.get("content", "OK")))
        except Exception as exc:
            self.events.put(("connection_error", str(exc)))

    def start_run(self):
        if self.running:
            return
        goal = self.goal.get("1.0", tk.END).strip()
        if not goal:
            messagebox.showwarning("缺少任务", "请输入任务目标。")
            return
        try:
            config = self._config()
        except Exception as exc:
            messagebox.showwarning("模型配置错误", str(exc))
            return
        self.running = True
        self.run_btn.configure(state=tk.DISABLED)
        self.clear_log()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.task_items.clear()
        self._set_state("运行中", COLORS["blue_dark"])
        self.append_log(f"MainAgent ← {goal}")
        execution_mode = self.execution_mode.get()
        threading.Thread(target=self._run_worker, args=(goal, config, execution_mode, None), daemon=True).start()

    def pause_run(self):
        if not self.running or self.active_controller is None:
            return
        self.active_controller.request_pause()
        self.pause_btn.configure(state=tk.DISABLED)
        self._set_state("已请求暂停，等待当前阶段安全结束", COLORS["blue_dark"])
        self.append_log("LONG → 已请求在当前阶段边界安全暂停")

    def show_run_history(self):
        RunHistoryDialog(self, LongHorizonStore(long_horizon_runs_root()), self.resume_run)

    def resume_run(self, state):
        if self.running:
            messagebox.showwarning("任务正在运行", "请先等待当前任务结束或暂停。")
            return
        try:
            config = self._config()
        except Exception as exc:
            messagebox.showwarning("模型配置错误", str(exc))
            return
        if not state.acceptance_contract:
            messagebox.showerror("无法恢复", "该历史任务没有持久化验收合同。")
            return
        self.goal.delete("1.0", tk.END)
        self.goal.insert("1.0", state.goal)
        self.execution_mode.set("长程任务")
        self.running = True
        self.run_btn.configure(state=tk.DISABLED)
        self.clear_log()
        self.append_log(f"RESUME → run_id={state.run_id} · phase={state.phase} · status={state.status}")
        self._set_state("正在恢复长程任务", COLORS["blue_dark"])
        threading.Thread(
            target=self._run_worker,
            args=(state.goal, config, "长程任务", state.run_id),
            daemon=True,
        ).start()

    def _run_worker(self, goal, config, execution_mode, resume_run_id=None):
        try:
            pipeline = PlanningPipeline()
            tool_test = execution_mode in DEVELOPER_EXECUTION_MODES
            repair_test = execution_mode == "失败修复自检"
            if tool_test:
                TOOL_TEST_WORKSPACE.mkdir(parents=True, exist_ok=True)
                if repair_test:
                    prepare_repair_fixture()
                    self.events.put(("fixture_ready", "已重置故障：hello.py 当前错误地执行减法"))
                plan = build_tool_test_plan(goal)
                domain = "tool_call_self_test"
                workspace = TOOL_TEST_WORKSPACE
            else:
                workspace = PROJECT_DIR
                if execution_mode == "标准多 Agent":
                    intent = pipeline.intent_parser.parse(goal)
                    drafts = pipeline.decomposer.decompose(intent)
                    drafts = pipeline.acceptance_generator.generate(intent, drafts)
                    plan = pipeline.planner.build(intent, drafts)
                    domain = intent.domain
            if execution_mode != "长程任务":
                self.events.put(("plan", (domain, plan)))
            client = OpenAICompatibleClient(config) if config else None

            def on_tool_event(event, payload):
                self.events.put(("tool_event", (event, payload)))

            registry = build_registry(
                client,
                workspace=workspace,
                on_tool_event=on_tool_event,
                tool_test=tool_test,
            )

            def on_event(event, task, result=None):
                self.events.put((
                    "task_event",
                    (event, task.id, result, task.metadata.get("runtime_attempt")),
                ))

            evaluator = AcceptanceEvaluator(workspace=workspace, execute_commands=tool_test) if client else None
            orchestrator = Orchestrator(registry, max_workers=4, on_event=on_event, acceptance=evaluator)
            if execution_mode == "长程任务":
                runs_root = long_horizon_runs_root()
                store = LongHorizonStore(runs_root)
                persisted_state = store.load(resume_run_id) if resume_run_id else None
                persisted_contract = None
                if persisted_state:
                    if not persisted_state.acceptance_contract:
                        raise ValueError("历史运行缺少验收合同，无法安全恢复")
                    persisted_contract = AcceptanceContract.from_dict(
                        persisted_state.acceptance_contract
                    )

                def on_long_event(event, payload):
                    self.events.put(("long_horizon_event", (event, payload)))

                def on_global_evaluator_event(event, payload):
                    self.events.put(("global_evaluator_event", (event, payload)))

                if client:
                    def on_replanner_event(event, payload):
                        self.events.put(("replanner_event", (event, payload)))

                    replanner = ResilientReplanner(
                        StructuredReplanner(
                            client,
                            max_attempts=max(1, int(self.replan_attempts.get())),
                            on_event=on_replanner_event,
                        ),
                        on_event=on_replanner_event,
                    )

                    baseline_plan = pipeline.build(goal)

                    def on_contract_event(event, payload):
                        self.events.put(("contract_event", (event, payload)))

                    domain = pipeline.intent_parser.parse(goal).domain
                    if persisted_contract:
                        contract = persisted_contract
                    else:
                        contract = StructuredGoalContractGenerator(
                            client,
                            on_event=on_contract_event,
                        ).generate(goal, plan_hint=baseline_plan, domain=domain)
                else:
                    replanner = DeterministicRecoveryPlanner()
                    baseline_plan = pipeline.build(goal)
                    contract = (
                        persisted_contract
                        if persisted_contract
                        else AcceptanceContract.from_plan(goal, baseline_plan)
                    )

                if not persisted_state:
                    # Execution gate: no controller, Agent, or tool starts before confirmation.
                    contract_reply = queue.Queue(maxsize=1)
                    self.events.put(("contract_preview_request", (contract, contract_reply)))
                    contract = contract_reply.get()
                    if contract is None:
                        self.events.put(("run_cancelled", "用户取消了验收合同，未启动 Agent 或工具"))
                        return
                ContractValidator().validate(contract, expected_goal=goal)
                self.events.put((
                    "contract_confirmed",
                    {
                        "criterion_count": len(contract.criteria),
                        "required_count": sum(item.required for item in contract.criteria),
                    },
                ))

                def on_initial_plan_event(event, payload):
                    self.events.put(("initial_plan_event", (event, payload)))

                skip_initial_generation = bool(
                    persisted_state and (persisted_state.phase > 0 or persisted_state.pending_plan)
                )
                initial_plan = None if skip_initial_generation else (
                    StructuredInitialDAGGenerator(
                        client,
                        on_event=on_initial_plan_event,
                    ).generate(contract, task_budget=50)
                    if client
                    else RuleBasedContractPlanner().build(contract, task_budget=50)
                )
                if initial_plan:
                    self.events.put(("contract_plan", initial_plan))

                if client:
                    global_evaluator = StructuredGlobalEvaluator(
                        client=client,
                        contract=contract,
                        workspace=workspace,
                        on_event=on_global_evaluator_event,
                    )
                else:
                    global_evaluator = DeterministicGlobalEvaluator(
                        contract=contract,
                        workspace=workspace,
                        on_event=on_global_evaluator_event,
                    )

                controller = LongHorizonController(
                    orchestrator=orchestrator,
                    initial_planner=lambda _state: initial_plan or RuleBasedContractPlanner().build(
                        contract, task_budget=50
                    ),
                    store=store,
                    evaluator=global_evaluator,
                    replanner=replanner,
                    max_phases=3,
                    max_total_tasks=50,
                    on_event=on_long_event,
                    acceptance_contract=contract.to_dict(),
                )
                self.active_controller = controller
                self.events.put(("controller_ready", None))
                report = controller.run(goal, run_id=resume_run_id, resume=bool(resume_run_id))
                self.events.put(("long_horizon_report", (report, store.state_path(report.state.run_id))))
            else:
                main = MainAgent(orchestrator, pipeline.build)
                report = main.orchestrator.run(plan)
                self.events.put(("report", report))
        except Exception as exc:
            self.events.put(("run_error", str(exc)))

    def _drain(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "connection":
                    self.test_btn.configure(state=tk.NORMAL)
                    self._set_state("模型连接成功", COLORS["success"])
                    messagebox.showinfo("连接成功", f"模型响应：{payload[:120]}")
                elif kind == "connection_error":
                    self.test_btn.configure(state=tk.NORMAL)
                    self._set_state("连接失败", COLORS["danger"])
                    messagebox.showerror("连接失败", payload)
                elif kind == "plan":
                    domain, plan = payload
                    self.append_log(f"IntentParser → domain={domain}")
                    self.append_log(f"Planner → {len(plan.subtasks)} 个子任务")
                    for task in plan.subtasks:
                        item = self.tree.insert("", tk.END, values=(task.id, task.role, ", ".join(task.depends_on) or "—", "等待", "—"))
                        self.task_items[task.id] = item
                elif kind == "report":
                    self._show_report(payload)
                elif kind == "task_event":
                    self._show_task_event(payload)
                elif kind == "tool_event":
                    self._show_tool_event(payload)
                elif kind == "long_horizon_event":
                    self._show_long_horizon_event(payload)
                elif kind == "long_horizon_report":
                    self._show_long_horizon_report(payload)
                elif kind == "replanner_event":
                    self._show_replanner_event(payload)
                elif kind == "initial_plan_event":
                    self._show_initial_plan_event(payload)
                elif kind == "global_evaluator_event":
                    self._show_global_evaluator_event(payload)
                elif kind == "contract_event":
                    self._show_contract_event(payload)
                elif kind == "contract_preview_request":
                    contract, reply_queue = payload
                    self._set_state("等待验收合同确认", COLORS["blue_dark"])
                    self.append_log("CONTRACT → 等待用户预览并确认；尚未启动 Agent 或工具")
                    ContractPreviewDialog(self, contract, reply_queue)
                elif kind == "contract_confirmed":
                    self.append_log(
                        "CONTRACT → 用户已确认合同 · "
                        f"criteria={payload['criterion_count']} · required={payload['required_count']}"
                    )
                    self._set_state("验收合同已确认，开始执行", COLORS["blue_dark"])
                elif kind == "contract_plan":
                    self.append_log(
                        f"CONTRACT PLANNER → 初始 DAG 已覆盖合同 · tasks={len(payload.subtasks)} · "
                        f"required={len(payload.final_acceptance)}"
                    )
                elif kind == "controller_ready":
                    self.pause_btn.configure(state=tk.NORMAL)
                elif kind == "run_cancelled":
                    self.append_log(f"CONTRACT → {payload}")
                    self.running = False
                    self.active_controller = None
                    self.run_btn.configure(state=tk.NORMAL)
                    self.pause_btn.configure(state=tk.DISABLED)
                    self._set_state("任务已取消", COLORS["muted"])
                elif kind == "fixture_ready":
                    self.append_log(f"FIXTURE → {payload}")
                elif kind == "run_error":
                    self.append_log("ERROR → " + payload)
                    self.running = False
                    self.active_controller = None
                    self.run_btn.configure(state=tk.NORMAL)
                    self.pause_btn.configure(state=tk.DISABLED)
                    self._set_state("任务失败", COLORS["danger"])
        except queue.Empty:
            pass
        self.after(100, self._drain)

    def _show_report(self, report: RunReport):
        for task_id, result in report.results.items():
            item = self.task_items.get(task_id)
            if item:
                vals = list(self.tree.item(item, "values"))
                vals[3] = result.status
                vals[4] = str(result.attempts)
                self.tree.item(item, values=vals)
            summary = result.summary.replace("\n", " ")[:180]
            self.append_log(f"{task_id} [{result.status}] → {summary}")
        self.append_log(f"MainAgent → status={report.status}, rounds={report.rounds}")
        self.running = False
        self.active_controller = None
        self.run_btn.configure(state=tk.NORMAL)
        self.pause_btn.configure(state=tk.DISABLED)
        color = COLORS["success"] if report.status == "success" else COLORS["danger"]
        self._set_state(f"完成 · {report.status} · {report.rounds} 轮", color)

    def _show_task_event(self, payload):
        event, task_id, result, runtime_attempt = payload
        item = self.task_items.get(task_id)
        vals = list(self.tree.item(item, "values")) if item else []
        if event == "task_started":
            if item:
                vals[3] = "执行中"
                vals[4] = str(runtime_attempt) if runtime_attempt is not None else "?"
            self.append_log(f"{task_id} → 子 Agent 开始执行" + (f" · attempt={runtime_attempt}" if runtime_attempt else ""))
        elif event == "task_finished" and result is not None:
            if item:
                vals[3] = result.status
                vals[4] = str(result.attempts)
            self.append_log(f"{task_id} → {result.status}")
        elif event == "task_retry_scheduled" and result is not None:
            reason = "; ".join(result.failures[:3]) or result.status
            self.append_log(
                f"RETRY → {task_id} · 第 {result.attempts} 次未通过 · "
                f"下一次将携带失败反馈 · {self._compact(reason, 260)}"
            )
            if item:
                vals[3] = "准备重试"
                vals[4] = str(result.attempts)
        if item and vals:
            self.tree.item(item, values=vals)

    def _show_tool_event(self, payload):
        event, detail = payload
        task_id = detail.get("task_id", "unknown")
        step = detail.get("step", "?")
        tool = detail.get("tool", "unknown")
        if event == "tool_started":
            arguments = self._compact(detail.get("arguments", {}), 240)
            self.append_log(f"TOOL #{step} · {task_id} · {tool} · args={arguments}")
            return
        success = detail.get("success", False)
        duration = float(detail.get("duration_seconds", 0.0))
        output = detail.get("output") or detail.get("error") or ""
        self.append_log(
            f"TOOL #{step} · {tool} · {'success' if success else 'failed'} · "
            f"{duration:.3f}s · {self._compact(output, 300)}"
        )

    def _show_long_horizon_event(self, payload):
        event, detail = payload
        if event == "run_started":
            self.append_log("LONG → 长程控制器已启动")
        elif event == "phase_planned":
            phase = detail.get("phase", "?")
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.task_items.clear()
            for task in detail.get("tasks", []):
                item = self.tree.insert(
                    "",
                    tk.END,
                    values=(
                        task.get("id", "unknown"),
                        task.get("role", "unknown"),
                        ", ".join(task.get("depends_on", [])) or "—",
                        "等待",
                        "—",
                    ),
                )
                self.task_items[task.get("id", "unknown")] = item
            self.append_log(
                f"PHASE {phase} → 已规划 {len(detail.get('tasks', []))} 个任务 · "
                f"{detail.get('plan_goal', '')}"
            )
            self._set_state(f"长程任务 · 阶段 {phase} 执行中", COLORS["blue_dark"])
        elif event == "phase_finished":
            phase = detail.get("phase", "?")
            verdict = "全局目标完成" if detail.get("completed") else "需要继续规划"
            self.append_log(f"PHASE {phase} → {verdict} · {detail.get('reason', '')}")
        elif event == "budget_exhausted":
            self.append_log(f"LONG → 预算耗尽 · {detail.get('reason', '')}")
        elif event == "run_failed":
            self.append_log(f"LONG → 运行失败 · {detail.get('reason', '')}")
        elif event == "run_completed":
            self.append_log(f"LONG → 最终目标已通过阶段 {detail.get('phase', '?')} 验收")
        elif event == "completed_run_audit_failed":
            missing = ", ".join(detail.get("missing_criteria", [])) or "unknown"
            self.append_log(f"AUDIT → 历史完成状态已撤销 · 缺失: {missing}")
        elif event == "completed_run_audit_passed":
            self.append_log("AUDIT → 历史完成状态已通过合同重新验收")
        elif event == "run_paused":
            self.append_log(
                f"LONG → 已在阶段 {detail.get('phase', '?')} 安全暂停 · {detail.get('boundary', '')}"
            )
        elif event == "replan_pending":
            self.append_log(
                f"LONG → 恢复规划暂不可用，运行已保存为可恢复状态 · {detail.get('reason', '')}"
            )

    def _show_long_horizon_report(self, payload):
        report, state_path = payload
        state = report.state
        self.append_log(
            f"LongHorizonController → status={state.status}, phases={state.phase}, "
            f"tasks={state.total_tasks}"
        )
        self.append_log(f"STATE → {state_path}")
        self.running = False
        self.active_controller = None
        self.run_btn.configure(state=tk.NORMAL)
        self.pause_btn.configure(state=tk.DISABLED)
        color = (
            COLORS["success"] if state.status == "completed"
            else COLORS["blue_dark"] if state.status == "paused"
            else COLORS["danger"]
        )
        self._set_state(f"长程任务 · {state.status} · {state.phase} 阶段", color)

    def _show_replanner_event(self, payload):
        event, detail = payload
        if event == "replan_started":
            self.append_log(
                f"REPLAN → 模型正在生成阶段 {detail.get('phase', '?')} 的恢复 DAG "
                f"· attempt={detail.get('attempt', '?')}"
            )
        elif event == "replan_validation_failed":
            self.append_log(
                f"REPLAN → 计划校验失败 · attempt={detail.get('attempt', '?')} · "
                f"{self._compact(detail.get('error', ''), 300)}"
            )
        elif event == "replan_completed":
            self.append_log(
                f"REPLAN → 结构化计划通过校验 · tasks={detail.get('task_count', 0)} · "
                f"{detail.get('phase_goal', '')}"
            )
        elif event == "replan_retry_wait":
            self.append_log(
                f"REPLAN → 请求失败，将在 {detail.get('delay_seconds', 0)} 秒后重试"
            )
        elif event == "replan_fallback_started":
            self.append_log(
                f"REPLAN → 模型恢复规划不可用，启用规则型恢复 · {self._compact(detail.get('error', ''), 220)}"
            )
        elif event == "replan_fallback_completed":
            self.append_log(f"REPLAN → 规则型恢复 DAG 已生成 · tasks={detail.get('task_count', 0)}")

    def _show_initial_plan_event(self, payload):
        event, detail = payload
        if event == "initial_plan_started":
            self.append_log(f"INITIAL DAG → 正在根据合同生成任务图 · attempt={detail.get('attempt', '?')}")
        elif event == "initial_plan_validation_failed":
            self.append_log(
                f"INITIAL DAG → 计划校验失败 · attempt={detail.get('attempt', '?')} · "
                f"{self._compact(detail.get('error', ''), 260)}"
            )
        elif event == "initial_plan_completed":
            self.append_log(f"INITIAL DAG → 合同原生任务图已通过校验 · tasks={detail.get('task_count', 0)}")
        elif event == "initial_plan_fallback":
            self.append_log(
                f"INITIAL DAG → 模型计划不可用，已启用规则型合同任务图 · tasks={detail.get('task_count', 0)}"
            )

    def _show_global_evaluator_event(self, payload):
        event, detail = payload
        if event == "global_hard_gate":
            verdict = "通过" if detail.get("passed") else "未通过"
            self.append_log(
                f"GLOBAL HARD GATE → {verdict} · passed={detail.get('passed_count', 0)} · "
                f"missing={detail.get('missing_count', 0)}"
            )
            for failure in detail.get("failures", [])[:5]:
                self.append_log(f"  MISSING → {self._compact(failure, 260)}")
        elif event == "global_semantic_started":
            self.append_log(
                f"GLOBAL SEMANTIC → 正在检查最终目标覆盖 · attempt={detail.get('attempt', '?')}"
            )
        elif event == "global_semantic_failed":
            self.append_log(
                f"GLOBAL SEMANTIC → 返回格式无效 · {self._compact(detail.get('error', ''), 260)}"
            )
        elif event == "global_semantic_completed":
            verdict = "最终目标完成" if detail.get("completed") else "仍有目标缺口"
            self.append_log(
                f"GLOBAL SEMANTIC → {verdict} · missing={detail.get('missing_criteria', [])}"
            )

    def _show_contract_event(self, payload):
        event, detail = payload
        if event == "contract_generation_started":
            self.append_log(
                f"CONTRACT → 正在生成最终验收合同 · attempt={detail.get('attempt', '?')}"
            )
        elif event == "contract_validation_failed":
            self.append_log(
                f"CONTRACT → 合同校验失败 · attempt={detail.get('attempt', '?')} · "
                f"{self._compact(detail.get('error', ''), 300)}"
            )
        elif event == "contract_generation_completed":
            self.append_log(
                f"CONTRACT → 验收合同已冻结 · criteria={detail.get('criterion_count', 0)} · "
                f"required={detail.get('required_count', 0)}"
            )
        elif event == "contract_fallback_completed":
            self.append_log(
                f"CONTRACT → 模型合同不可用，已启用规则型安全合同 · "
                f"criteria={detail.get('criterion_count', 0)} · required={detail.get('required_count', 0)}"
            )

    @staticmethod
    def _compact(value, limit):
        import json

        text = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        text = " ".join(text.split())
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def _set_state(self, text, color):
        self.status.set(text)
        self.status_dot.configure(fg=color)

    def append_log(self, text):
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def clear_log(self):
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)


if __name__ == "__main__":
    FreshUI().mainloop()
