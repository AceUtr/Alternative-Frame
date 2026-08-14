"""Read-only evaluation views for the competition UI.

This module deliberately does not modify core execution state.
It only reads generated evaluation artifacts and converts them
into presentation-friendly structures.

The main UI may import these helpers without coupling benchmark
logic to Tkinter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_REPORT = Path(
    "reports/unified_evaluation_v2/"
    "competition_evaluation.json"
)


def load_competition_evaluation(
    path: str | Path = DEFAULT_REPORT,
) -> Dict[str, Any]:
    source = Path(path)

    if not source.exists():
        raise FileNotFoundError(
            f"evaluation report not found: {source}"
        )

    return json.loads(
        source.read_text(encoding="utf-8")
    )


def agent_summary(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    rows = [
        row
        for row in payload.get("rows", [])
        if row.get("experiment") == "agent_topology"
    ]

    lookup = {
        row["condition"]: row
        for row in rows
    }

    single = lookup.get("single_agent", {})
    multi = lookup.get("multi_agent", {})

    single_duration = single.get(
        "mean_duration_seconds"
    )
    multi_duration = multi.get(
        "mean_duration_seconds"
    )

    speedup = None

    if (
        isinstance(single_duration, (int, float))
        and isinstance(multi_duration, (int, float))
        and multi_duration > 0
    ):
        speedup = (
            single_duration / multi_duration
        )

    return {
        "single_completion_rate": single.get(
            "goal_completion_rate"
        ),
        "multi_completion_rate": multi.get(
            "goal_completion_rate"
        ),
        "single_duration_seconds": single_duration,
        "multi_duration_seconds": multi_duration,
        "wall_clock_speedup": speedup,
        "single_backend_count": single.get(
            "unique_backend_count"
        ),
        "multi_backend_count": multi.get(
            "unique_backend_count"
        ),
    }


def recovery_summary(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    rows = [
        row
        for row in payload.get("rows", [])
        if row.get("experiment") == "local_recovery"
    ]

    lookup = {
        row["condition"]: row
        for row in rows
    }

    off = lookup.get("recovery_off", {})
    on = lookup.get("recovery_on", {})

    return {
        "off_completed": bool(
            off.get("goal_completion_rate")
        ),
        "on_completed": bool(
            on.get("goal_completion_rate")
        ),
        "off_result": off.get("key_result"),
        "on_result": on.get("key_result"),
    }


def contract_summary(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    rows = [
        row
        for row in payload.get("rows", [])
        if row.get("experiment")
        == "contract_validation"
    ]

    lookup = {
        row["condition"]: row
        for row in rows
    }

    off = lookup.get("contract_off", {})
    on = lookup.get("contract_on", {})

    return {
        "without_contract_declared_complete": bool(
            off.get("goal_completion_rate")
        ),
        "with_contract_declared_complete": bool(
            on.get("goal_completion_rate")
        ),
        "without_contract_result": off.get(
            "key_result"
        ),
        "with_contract_result": on.get(
            "key_result"
        ),
    }


def overview_cards(
    payload: Dict[str, Any],
) -> List[Dict[str, str]]:
    agent = agent_summary(payload)
    recovery = recovery_summary(payload)
    contract = contract_summary(payload)

    speedup = agent.get(
        "wall_clock_speedup"
    )

    speedup_text = (
        f"{speedup:.3f}x"
        if isinstance(speedup, (int, float))
        else "unknown"
    )

    return [
        {
            "title": "Multi-Agent Speedup",
            "value": speedup_text,
            "detail": (
                "Deterministic orchestration "
                "parallelism only"
            ),
        },
        {
            "title": "Local Recovery",
            "value": (
                "PASS"
                if recovery["on_completed"]
                and not recovery["off_completed"]
                else "CHECK"
            ),
            "detail": (
                "Recovery OFF failed; "
                "Recovery ON completed"
            ),
        },
        {
            "title": "Contract Gate",
            "value": (
                "PASS"
                if (
                    contract[
                        "without_contract_declared_complete"
                    ]
                    and not contract[
                        "with_contract_declared_complete"
                    ]
                )
                else "CHECK"
            ),
            "detail": (
                "Contract validation blocks "
                "false completion"
            ),
        },
        {
            "title": "Live LLM",
            "value": (
                "AVAILABLE"
                if payload.get(
                    "live_llm_available"
                )
                else "PENDING"
            ),
            "detail": (
                "Live API ablations are kept "
                "separate from deterministic evidence"
            ),
        },
    ]


def format_overview_text(
    payload: Dict[str, Any],
) -> str:
    lines = []

    for card in overview_cards(payload):
        lines.append(
            f"{card['title']}: "
            f"{card['value']}"
        )
        lines.append(
            f"  {card['detail']}"
        )

    return "\n".join(lines)


def create_tk_evaluation_panel(
    parent,
    path: str | Path = DEFAULT_REPORT,
):
    """Optional Tkinter panel for the main UI.

    Main UI owners can import this function without
    changing any benchmark execution logic.
    """
    import tkinter as tk
    from tkinter import ttk

    frame = ttk.Frame(parent)

    title = ttk.Label(
        frame,
        text="Evaluation Overview",
    )
    title.pack(
        anchor="w",
        padx=8,
        pady=(8, 4),
    )

    text = tk.Text(
        frame,
        height=14,
        width=70,
        wrap="word",
    )

    text.pack(
        fill="both",
        expand=True,
        padx=8,
        pady=(0, 8),
    )

    try:
        payload = load_competition_evaluation(
            path
        )
        content = format_overview_text(
            payload
        )
    except Exception as exc:
        content = (
            "Evaluation data unavailable.\n\n"
            f"{type(exc).__name__}: {exc}"
        )

    text.insert("1.0", content)
    text.configure(state="disabled")

    return frame
