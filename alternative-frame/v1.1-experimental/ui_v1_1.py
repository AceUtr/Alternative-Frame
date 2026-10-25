"""Alternative-Frame v1.1 experimental control room.

This is intentionally separate from ``ui.py``: it visualizes and exercises the
opt-in runtime modules without changing the v1.0 interface or execution path.
"""

from __future__ import annotations

import json
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tempfile import TemporaryDirectory

from core.experimental import (
    BoundedMessageBus,
    CostBudget,
    CostGuard,
    HybridMemory,
    JsonlEventLog,
    TaskQueue,
    Usage,
)


COLORS = {
    "bg": "#F4FAF8", "card": "#FFFFFF", "mint": "#DDF4EC",
    "mint_dark": "#2E7D68", "blue": "#E7F0FF", "blue_dark": "#315F96",
    "text": "#24332F", "muted": "#71817B", "line": "#DCE9E4",
    "success": "#2F8F6B", "danger": "#B85C5C", "amber": "#B47B29",
}


class ExperimentalUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Alternative Frame · v1.1 实验控制台")
        self.geometry("1220x820")
        self.minsize(980, 680)
        self.configure(bg=COLORS["bg"])
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._temp = TemporaryDirectory(prefix="alternative-frame-ui-")
        self.root = Path(self._temp.name)
        self.event_log = JsonlEventLog(self.root / "events.jsonl")
        self.budget = CostGuard(CostBudget(max_requests=20, max_tokens=12000, max_cost_usd=1.0))
        self.task_queue = TaskQueue(self.root / "tasks.sqlite3")
        self.bus = BoundedMessageBus({"main": {"researcher", "reviewer"}, "researcher": {"main"}, "reviewer": {"main"}})
        self.memory = HybridMemory()
        self._style()
        self._layout()
        self.after(100, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Hero.TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Sub.TLabel", background=COLORS["bg"], foreground=COLORS["muted"], font=("Microsoft YaHei UI", 10))
        style.configure("CardTitle.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Accent.TButton", background=COLORS["mint_dark"], foreground="white", padding=(14, 8), font=("Microsoft YaHei UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#266A59")])
        style.configure("Soft.TButton", background=COLORS["mint"], foreground=COLORS["mint_dark"], padding=(10, 7))
        style.configure("Treeview", background="white", fieldbackground="white", foreground=COLORS["text"], rowheight=28, borderwidth=0)
        style.configure("Treeview.Heading", background=COLORS["mint"], foreground=COLORS["mint_dark"], font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("TNotebook", background=COLORS["card"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6))

    def _card(self, parent):
        return tk.Frame(parent, bg=COLORS["card"], highlightbackground=COLORS["line"], highlightthickness=1, bd=0)

    def _layout(self):
        outer = tk.Frame(self, bg=COLORS["bg"], padx=22, pady=18)
        outer.pack(fill=tk.BOTH, expand=True)
        header = tk.Frame(outer, bg=COLORS["bg"])
        header.pack(fill=tk.X, pady=(0, 14))
        ttk.Label(header, text="Alternative Frame", style="Hero.TLabel").pack(anchor=tk.W)
        ttk.Label(header, text="v1.1 实验控制台  ·  运行时治理、协作队列与混合记忆", style="Sub.TLabel").pack(anchor=tk.W, pady=(3, 0))

        top = tk.Frame(outer, bg=COLORS["bg"])
        top.pack(fill=tk.X, pady=(0, 12))
        self._run_card(top)
        self._budget_card(top)

        content = tk.Frame(outer, bg=COLORS["bg"])
        content.pack(fill=tk.BOTH, expand=True)
        left = self._card(content); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        right = self._card(content); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(6, 0))
        self._queue_card(left)
        self._memory_card(left)
        self._communication_card(right)
        self._event_card(right)

        self.status = tk.StringVar(value="就绪 · 当前所有增强模块均为离线本地运行")
        tk.Label(outer, textvariable=self.status, bg=COLORS["bg"], fg=COLORS["muted"], anchor=tk.W, font=("Microsoft YaHei UI", 9)).pack(fill=tk.X, pady=(10, 0))

    def _run_card(self, parent):
        card = self._card(parent); card.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        inner = tk.Frame(card, bg=COLORS["card"], padx=14, pady=12); inner.pack(fill=tk.X)
        ttk.Label(inner, text="01 运行入口", style="CardTitle.TLabel").pack(anchor=tk.W)
        row = tk.Frame(inner, bg=COLORS["card"]); row.pack(fill=tk.X, pady=(9, 0))
        self.mode = tk.StringVar(value="离线增强演示")
        ttk.Combobox(row, textvariable=self.mode, state="readonly", width=18, values=("离线增强演示", "仅查看状态")).pack(side=tk.LEFT)
        ttk.Button(row, text="运行组合演示  →", style="Accent.TButton", command=self.run_demo).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(row, text="清空事件", style="Soft.TButton", command=self.clear_events).pack(side=tk.RIGHT)

    def _budget_card(self, parent):
        card = self._card(parent); card.pack(side=tk.LEFT, fill=tk.X, padx=(6, 0))
        inner = tk.Frame(card, bg=COLORS["card"], padx=14, pady=12); inner.pack(fill=tk.X)
        ttk.Label(inner, text="02 成本护栏", style="CardTitle.TLabel").pack(anchor=tk.W)
        self.budget_text = tk.StringVar(value="0 请求  ·  0 Token  ·  $0.0000")
        tk.Label(inner, textvariable=self.budget_text, bg=COLORS["card"], fg=COLORS["blue_dark"], font=("Cascadia Mono", 10)).pack(anchor=tk.W, pady=(9, 0))
        ttk.Button(inner, text="模拟一次模型调用", style="Soft.TButton", command=self.account_call).pack(anchor=tk.W, pady=(7, 0))

    def _queue_card(self, parent):
        box = tk.Frame(parent, bg=COLORS["card"], padx=14, pady=12); box.pack(fill=tk.X)
        ttk.Label(box, text="03 Agent 任务队列", style="CardTitle.TLabel").pack(anchor=tk.W)
        row = tk.Frame(box, bg=COLORS["card"]); row.pack(fill=tk.X, pady=(8, 6))
        self.task_goal = tk.StringVar(value="审查一个候选结果")
        ttk.Entry(row, textvariable=self.task_goal).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="入队并认领", style="Soft.TButton", command=self.enqueue_task).pack(side=tk.LEFT, padx=(8, 0))
        self.queue_tree = ttk.Treeview(box, columns=("id", "owner", "status", "attempt"), show="headings", height=4)
        for key, title, width in (("id", "任务", 120), ("owner", "Agent", 90), ("status", "状态", 90), ("attempt", "次数", 55)):
            self.queue_tree.heading(key, text=title); self.queue_tree.column(key, width=width, anchor=tk.W)
        self.queue_tree.pack(fill=tk.X)

    def _memory_card(self, parent):
        box = tk.Frame(parent, bg=COLORS["card"], padx=14, pady=12); box.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(box, text="04 混合记忆", style="CardTitle.TLabel").pack(anchor=tk.W)
        row = tk.Frame(box, bg=COLORS["card"]); row.pack(fill=tk.X, pady=(8, 6))
        self.memory_query = tk.StringVar(value="fallback API")
        ttk.Entry(row, textvariable=self.memory_query).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="检索", style="Soft.TButton", command=self.search_memory).pack(side=tk.LEFT, padx=(8, 0))
        self.memory_list = tk.Listbox(box, height=4, bg="#F8FBFA", fg=COLORS["text"], relief=tk.FLAT, highlightthickness=1, highlightbackground=COLORS["line"])
        self.memory_list.pack(fill=tk.X)

    def _communication_card(self, parent):
        box = tk.Frame(parent, bg=COLORS["card"], padx=14, pady=12); box.pack(fill=tk.X)
        ttk.Label(box, text="05 有界通信", style="CardTitle.TLabel").pack(anchor=tk.W)
        row = tk.Frame(box, bg=COLORS["card"]); row.pack(fill=tk.X, pady=(8, 6))
        self.recipient = tk.StringVar(value="researcher")
        ttk.Combobox(row, textvariable=self.recipient, state="readonly", width=13, values=("researcher", "reviewer")).pack(side=tk.LEFT)
        self.message_text = tk.StringVar(value="请检查候选结果")
        ttk.Entry(row, textvariable=self.message_text).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        ttk.Button(row, text="发送", style="Soft.TButton", command=self.send_message).pack(side=tk.LEFT, padx=(8, 0))
        self.comm_label = tk.StringVar(value="main → researcher · 等待消息")
        tk.Label(box, textvariable=self.comm_label, bg=COLORS["card"], fg=COLORS["muted"], anchor=tk.W).pack(fill=tk.X)

    def _event_card(self, parent):
        box = tk.Frame(parent, bg=COLORS["card"], padx=14, pady=12); box.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        ttk.Label(box, text="06 事件审计", style="CardTitle.TLabel").pack(anchor=tk.W)
        self.events = tk.Text(box, height=12, state=tk.DISABLED, wrap=tk.WORD, bg="#F8FBFA", fg=COLORS["text"], relief=tk.FLAT, highlightthickness=1, highlightbackground=COLORS["line"], font=("Cascadia Mono", 9))
        self.events.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

    def _emit(self, event, payload):
        self.event_log.emit(event, payload)
        self._events.put((event, payload))

    def _drain_events(self):
        try:
            while True:
                event, payload = self._events.get_nowait()
                self.events.configure(state=tk.NORMAL)
                self.events.insert(tk.END, json.dumps({"event": event, "payload": payload}, ensure_ascii=False) + "\n")
                self.events.see(tk.END); self.events.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def update_budget(self):
        snap = self.budget.snapshot()
        self.budget_text.set(f"{snap['requests']} 请求  ·  {snap['total_tokens']} Token  ·  ${snap['cost_usd']:.4f}")

    def account_call(self):
        try:
            reservation = self.budget.reserve(Usage(120, 80)); self.budget.settle(reservation, Usage(105, 64))
            self.update_budget(); self._emit("model_call_accounted", self.budget.snapshot())
            self.status.set("已完成一次本地 usage 对账")
        except Exception as exc:
            self.status.set(f"预算拒绝：{exc}"); self._emit("budget_rejected", {"error": str(exc)})

    def enqueue_task(self):
        task_id = self.task_queue.enqueue({"goal": self.task_goal.get()})
        claimed = self.task_queue.claim("reviewer")
        self.task_queue.ack(task_id, "reviewer", {"status": "accepted"})
        row = self.task_queue.get(task_id)
        self.queue_tree.insert("", tk.END, values=(task_id[:10], row["owner"] or "reviewer", "已完成", row["attempts"]))
        self._emit("task_completed", row); self.status.set("任务已入队、认领并 ACK")

    def send_message(self):
        try:
            msg = self.bus.send("main", self.recipient.get(), {"text": self.message_text.get()})
            received = self.bus.receive(self.recipient.get())
            self.comm_label.set(f"main → {self.recipient.get()} · 已接收 {len(received)} 条")
            self._emit("message_received", {"id": msg.id, "recipient": msg.recipient})
        except Exception as exc:
            messagebox.showerror("通信失败", str(exc), parent=self)

    def search_memory(self):
        self.memory_list.delete(0, tk.END)
        results = self.memory.search("strategy", self.memory_query.get())
        for item in results:
            self.memory_list.insert(tk.END, item["content"][:100])
        self._emit("memory_search", {"query": self.memory_query.get(), "hits": len(results)})

    def run_demo(self):
        def worker():
            self._emit("demo_started", {"mode": self.mode.get()})
            self.account_call_threadsafe()
            task_id = self.task_queue.enqueue({"goal": "离线组合演示"})
            claim = self.task_queue.claim("researcher")
            self.task_queue.ack(task_id, "researcher", {"status": "accepted"})
            self._emit("task_completed", self.task_queue.get(task_id))
            self._emit("demo_completed", {"task_id": task_id, "event_log": str(self.root / "events.jsonl")})
            self.after(0, lambda: self.status.set("离线增强演示完成 · 没有调用外部 API"))
        threading.Thread(target=worker, daemon=True).start()

    def account_call_threadsafe(self):
        reservation = self.budget.reserve(Usage(120, 80)); self.budget.settle(reservation, Usage(105, 64))
        self.after(0, self.update_budget); self._emit("model_call_accounted", self.budget.snapshot())

    def clear_events(self):
        self.events.configure(state=tk.NORMAL); self.events.delete("1.0", tk.END); self.events.configure(state=tk.DISABLED)
        self.status.set("界面事件已清空；磁盘事件日志仍保留在当前运行目录")

    def _close(self):
        self._temp.cleanup(); self.destroy()


if __name__ == "__main__":
    ExperimentalUI().mainloop()
