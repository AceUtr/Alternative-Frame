"""Fresh interactive UI v0.1 with user-selectable model API."""

from __future__ import annotations

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
    LongHorizonController,
    LongHorizonStore,
    ReportStatusEvaluator,
    StructuredGlobalEvaluator,
    StructuredReplanner,
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


class FreshUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Alternative Frame · v0.1")
        self.geometry("1180x790")
        self.minsize(980, 680)
        self.configure(bg=COLORS["bg"])
        self.events = queue.Queue()
        self.running = False
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
        self.test_btn = ttk.Button(inner, text="测试连接", style="Soft.TButton", command=self.test_connection)
        self.test_btn.grid(row=7, column=1, sticky=tk.E, pady=(9, 0))
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
        return ModelConfig(
            base_url=self.base_url.get().strip().rstrip("/"),
            api_key=self.api_key.get().strip(),
            model=self.model_name.get().strip(),
            temperature=float(self.temperature.get()),
            max_tokens=int(self.max_tokens.get()),
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
        threading.Thread(target=self._run_worker, args=(goal, config, execution_mode), daemon=True).start()

    def _run_worker(self, goal, config, execution_mode):
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
                self.events.put(("task_event", (event, task.id, result)))

            evaluator = AcceptanceEvaluator(workspace=workspace, execute_commands=tool_test) if client else None
            orchestrator = Orchestrator(registry, max_workers=4, on_event=on_event, acceptance=evaluator)
            if execution_mode == "长程任务":
                runs_root = Path(
                    os.getenv("LONG_HORIZON_RUNS_DIR", str(PROJECT_DIR / "runs" / "long_horizon"))
                )
                store = LongHorizonStore(runs_root)

                def on_long_event(event, payload):
                    self.events.put(("long_horizon_event", (event, payload)))

                if client:
                    def on_replanner_event(event, payload):
                        self.events.put(("replanner_event", (event, payload)))

                    replanner = StructuredReplanner(client, on_event=on_replanner_event)

                    def on_global_evaluator_event(event, payload):
                        self.events.put(("global_evaluator_event", (event, payload)))

                    initial_plan = pipeline.build(goal)
                    global_evaluator = StructuredGlobalEvaluator(
                        client=client,
                        contract=AcceptanceContract.from_plan(goal, initial_plan),
                        workspace=workspace,
                        on_event=on_global_evaluator_event,
                    )
                else:
                    replanner = lambda state, evaluation: build_recovery_plan(pipeline, state, evaluation)
                    initial_plan = pipeline.build(goal)
                    global_evaluator = ReportStatusEvaluator()

                controller = LongHorizonController(
                    orchestrator=orchestrator,
                    initial_planner=lambda _state: initial_plan,
                    store=store,
                    evaluator=global_evaluator,
                    replanner=replanner,
                    max_phases=3,
                    max_total_tasks=50,
                    on_event=on_long_event,
                )
                report = controller.run(goal)
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
                elif kind == "global_evaluator_event":
                    self._show_global_evaluator_event(payload)
                elif kind == "fixture_ready":
                    self.append_log(f"FIXTURE → {payload}")
                elif kind == "run_error":
                    self.append_log("ERROR → " + payload)
                    self.running = False
                    self.run_btn.configure(state=tk.NORMAL)
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
                vals[4] = result.attempts
                self.tree.item(item, values=vals)
            summary = result.summary.replace("\n", " ")[:180]
            self.append_log(f"{task_id} [{result.status}] → {summary}")
        self.append_log(f"MainAgent → status={report.status}, rounds={report.rounds}")
        self.running = False
        self.run_btn.configure(state=tk.NORMAL)
        color = COLORS["success"] if report.status == "success" else COLORS["danger"]
        self._set_state(f"完成 · {report.status} · {report.rounds} 轮", color)

    def _show_task_event(self, payload):
        event, task_id, result = payload
        item = self.task_items.get(task_id)
        if not item:
            return
        vals = list(self.tree.item(item, "values"))
        if event == "task_started":
            vals[3] = "执行中"
            self.append_log(f"{task_id} → 子 Agent 开始执行")
        elif event == "task_finished" and result is not None:
            vals[3] = result.status
            vals[4] = result.attempts
            self.append_log(f"{task_id} → {result.status}")
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

    def _show_long_horizon_report(self, payload):
        report, state_path = payload
        state = report.state
        self.append_log(
            f"LongHorizonController → status={state.status}, phases={state.phase}, "
            f"tasks={state.total_tasks}"
        )
        self.append_log(f"STATE → {state_path}")
        self.running = False
        self.run_btn.configure(state=tk.NORMAL)
        color = COLORS["success"] if state.status == "completed" else COLORS["danger"]
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
