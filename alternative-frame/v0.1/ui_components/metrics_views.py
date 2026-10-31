"""Read-only evaluation views for the competition UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_REPORT = Path(
    "reports/competition_final/"
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


def _experiment_rows(
    payload: Dict[str, Any],
    experiment: str,
) -> Dict[str, Dict[str, Any]]:
    return {
        row["condition"]: row
        for row in payload.get("rows", [])
        if row.get("experiment") == experiment
    }


def agent_summary(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    rows = _experiment_rows(
        payload,
        "agent_topology",
    )

    single = rows.get("single_agent", {})
    multi = rows.get("multi_agent", {})

    single_duration = single.get(
        "mean_duration_seconds"
    )
    multi_duration = multi.get(
        "mean_duration_seconds"
    )

    # Final competition report stores the latest value directly.
    speedup = payload.get(
        "agent_speedup"
    )

    if speedup is None and (
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
    rows = _experiment_rows(
        payload,
        "local_recovery",
    )

    off = rows.get("recovery_off", {})
    on = rows.get("recovery_on", {})

    return {
        "off_completed": bool(
            off.get(
                "completed",
                off.get("goal_completion_rate"),
            )
        ),
        "on_completed": bool(
            on.get(
                "completed",
                on.get("goal_completion_rate"),
            )
        ),
        "off_result": off.get("result")
        or off.get("key_result"),
        "on_result": on.get("result")
        or on.get("key_result"),
    }


def contract_summary(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    rows = _experiment_rows(
        payload,
        "contract_validation",
    )

    off = rows.get("contract_off", {})
    on = rows.get("contract_on", {})

    return {
        "without_contract_declared_complete": bool(
            off.get(
                "completed",
                off.get("goal_completion_rate"),
            )
        ),
        "with_contract_declared_complete": bool(
            on.get(
                "completed",
                on.get("goal_completion_rate"),
            )
        ),
        "without_contract_result": off.get("result")
        or off.get("key_result"),
        "with_contract_result": on.get("result")
        or on.get("key_result"),
    }


def routing_summary(
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    rows = _experiment_rows(
        payload,
        "routing",
    )

    fixed = rows.get("fixed_cloud", {})
    dynamic = rows.get("dynamic_routing", {})

    routing_result = payload.get(
        "routing_result",
        {},
    )

    return {
        "fixed_completed": bool(
            fixed.get(
                "completed",
                routing_result.get(
                    "fixed_cloud_completed"
                ),
            )
        ),
        "dynamic_completed": bool(
            dynamic.get(
                "completed",
                routing_result.get(
                    "dynamic_completed"
                ),
            )
        ),
        "dynamic_final_node": (
            routing_result.get(
                "dynamic_final_node"
            )
        ),
        "fallback_count": (
            routing_result.get(
                "fallback_count"
            )
        ),
        "fixed_result": fixed.get("result"),
        "dynamic_result": dynamic.get("result"),
    }


def overview_cards(
    payload: Dict[str, Any],
) -> List[Dict[str, str]]:
    agent = agent_summary(payload)
    recovery = recovery_summary(payload)
    contract = contract_summary(payload)
    routing = routing_summary(payload)

    speedup = agent.get(
        "wall_clock_speedup"
    )

    speedup_text = (
        f"{speedup:.3f}x"
        if isinstance(speedup, (int, float))
        else "unknown"
    )

    routing_pass = (
        not routing["fixed_completed"]
        and routing["dynamic_completed"]
        and routing["dynamic_final_node"] == "edge"
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
            "title": "Dynamic Routing",
            "value": (
                "PASS"
                if routing_pass
                else "CHECK"
            ),
            "detail": (
                "Fixed Cloud failed; "
                "Cloud→Edge fallback completed"
            ),
        },
        {
            "title": "Live LLM",
            "value": "PENDING",
            "detail": (
                "Optional live-model evidence "
                "remains separate"
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
        height=16,
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
