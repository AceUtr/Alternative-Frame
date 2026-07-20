"""Interactive UI v0 for Alternative Frame.

Run from this directory:
    python ui_v0.py

The UI deliberately uses tkinter from the Python standard library and calls the
same planning/orchestration objects as run_demo.py. No web server or dependency
installation is needed for v0.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict

from core.agents import AgentRegistry, DeterministicAgent
from core.main_agent import MainAgent
from core.orchestrator import Orchestrator, RunReport
from core.planning import PlanningPipeline


class UiAgent(DeterministicAgent):
    """Deterministic v0 agent with a small delay so progress is visible."""

    def run(self, task, context):
        import time
        time.sleep(0.15)
        return super().run(task, context)


def build_runtime() -> MainAgent:
    registry = AgentRegistry()
    roles = [
        "researcher", "experimenter", "reviewer",
        "analyst", "architect", "developer", "tester",
    ]
    for role in roles:
        registry.register(UiAgent(role))
    orchestrator = Orchestrator(registry, max_workers=4)
    return MainAgent(orchestrator, PlanningPipeline().build)


class AlternativeFrameApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Alternative Frame - Multi-Agent Harness v0")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.events: queue.Queue = queue.Queue()
        self.running = False
        self.task_items: Dict[str, str] = {}
        self._build_style()
        self._build_layout()
        self.after(100, self._drain_events)

    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"), foreground="#1f4d78")
        style.configure("Section.TLabel", font=("Segoe UI", 11, "bold"), foreground="#2e74b5")
        style.configure("Run.TButton", font=("Segoe UI", 10, "bold"))

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill=tk.BOTH, expand=True)
        ttk.Label(root, text="Alternative Frame", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(root, text="主 Agent 规划 · 子 Agent 编排 · 任务结果回放 v0").pack(anchor=tk.W, pady=(2, 14))

        input_frame = ttk.LabelFrame(root, text="任务输入", padding=10)
        input_frame.pack(fill=tk.X)
        ttk.Label(input_frame, text="自然语言目标").grid(row=0, column=0, sticky=tk.NW, padx=(0, 8))
        self.goal = tk.Text(input_frame, height=4, wrap=tk.WORD)
        self.goal.grid(row=0, column=1, sticky=tk.EW)
        self.goal.insert("1.0", "开发一个 FastAPI 服务，需要测试和 API 文档")
        input_frame.columnconfigure(1, weight=1)

        controls = ttk.Frame(input_frame)
        controls.grid(row=1, column=1, sticky=tk.W, pady=(8, 0))
        ttk.Label(controls, text="领域").pack(side=tk.LEFT)
        self.domain = tk.StringVar(value="自动识别")
        ttk.Combobox(controls, textvariable=self.domain, state="readonly", width=14,
                     values=["自动识别", "科研", "软件工程"]).pack(side=tk.LEFT, padx=(6, 16))
        self.run_button = ttk.Button(controls, text="▶ 运行任务", style="Run.TButton", command=self.start_run)
        self.run_button.pack(side=tk.LEFT)
        ttk.Button(controls, text="清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=8)

        body = ttk.PanedWindow(root, orient=tk.VERTICAL)
        body.pack(fill=tk.BOTH, expand=True, pady=(14, 0))

        task_frame = ttk.LabelFrame(body, text="任务 DAG / 子 Agent 状态", padding=8)
        body.add(task_frame, weight=3)
        columns = ("task", "role", "depends", "status", "attempts", "artifact")
        self.tree = ttk.Treeview(task_frame, columns=columns, show="headings", height=10)
        headings = {"task": "子任务", "role": "角色", "depends": "依赖", "status": "状态", "attempts": "尝试次数", "artifact": "产物"}
        widths = {"task": 150, "role": 130, "depends": 170, "status": 90, "attempts": 90, "artifact": 240}
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor=tk.W)
        scrollbar = ttk.Scrollbar(task_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        log_frame = ttk.LabelFrame(body, text="运行日志", padding=8)
        body.add(log_frame, weight=2)
        self.log = tk.Text(log_frame, height=8, wrap=tk.WORD, state=tk.DISABLED, background="#101820", foreground="#dce6ef")
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.status = tk.StringVar(value="就绪：输入目标后点击运行")
        ttk.Label(root, textvariable=self.status).pack(anchor=tk.W, pady=(8, 0))

    def clear_log(self) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.delete("1.0", tk.END)
        self.log.configure(state=tk.DISABLED)

    def append_log(self, line: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, line + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def start_run(self) -> None:
        if self.running:
            return
        goal = self.goal.get("1.0", tk.END).strip()
        if not goal:
            messagebox.showwarning("缺少任务", "请输入自然语言任务目标。")
            return
        self.running = True
        self.run_button.configure(state=tk.DISABLED)
        self.task_items.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.clear_log()
        self.status.set("规划中...")
        self.append_log(f"[MainAgent] 收到目标：{goal}")
        threading.Thread(target=self._worker, args=(goal,), daemon=True).start()

    def _worker(self, goal: str) -> None:
        try:
            runtime = build_runtime()
            pipeline = PlanningPipeline()
            intent = pipeline.intent_parser.parse(goal)
            drafts = pipeline.decomposer.decompose(intent)
            drafts = list(pipeline.acceptance_generator.generate(intent, drafts))
            plan = pipeline.planner.build(intent, drafts)
            self.events.put(("plan", plan))
            self.events.put(("log", f"[IntentParser] domain={intent.domain}"))
            self.events.put(("log", f"[Planner] 生成 {len(plan.subtasks)} 个子任务"))
            report = runtime.orchestrator.run(plan)
            self.events.put(("report", report))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "plan":
                    self._show_plan(payload)
                elif kind == "log":
                    self.append_log(payload)
                elif kind == "report":
                    self._show_report(payload)
                elif kind == "error":
                    self.append_log(f"[ERROR] {payload}")
                    self.status.set("运行失败")
                    self.running = False
                    self.run_button.configure(state=tk.NORMAL)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _show_plan(self, plan) -> None:
        for task in plan.subtasks:
            item = self.tree.insert("", tk.END, values=(task.id, task.role, ", ".join(task.depends_on) or "-", "queued", "-", "-"))
            self.task_items[task.id] = item
        self.status.set("执行中：子 Agent 正在完成任务")
        self.append_log("[Orchestrator] 开始执行任务 DAG")

    def _show_report(self, report: RunReport) -> None:
        for task_id, result in report.results.items():
            item = self.task_items.get(task_id)
            if item:
                values = list(self.tree.item(item, "values"))
                values[3] = result.status
                values[4] = str(result.attempts)
                values[5] = ", ".join(result.artifacts) or "-"
                self.tree.item(item, values=values)
            self.append_log(f"[{task_id}] {result.status} | {result.summary}")
        self.append_log(f"[MainAgent] 总结：status={report.status}, rounds={report.rounds}")
        self.status.set(f"完成：{report.status}，执行轮次 {report.rounds}")
        self.running = False
        self.run_button.configure(state=tk.NORMAL)


if __name__ == "__main__":
    app = AlternativeFrameApp()
    app.mainloop()

