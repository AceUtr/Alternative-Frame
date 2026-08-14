"""Recovery-mode configuration for controlled ablation experiments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from core.local_recovery import LocalDAGRecoveryController


RecoveryMode = Literal["none", "phase", "full"]


@dataclass(frozen=True)
class RecoverySettings:
    mode: RecoveryMode
    max_phases: int
    enable_phase_replanning: bool
    enable_local_recovery: bool
    local_recovery_max_cycles: int


MODES = {
    "none": RecoverySettings(
        mode="none",
        max_phases=1,
        enable_phase_replanning=False,
        enable_local_recovery=False,
        local_recovery_max_cycles=0,
    ),
    "phase": RecoverySettings(
        mode="phase",
        max_phases=3,
        enable_phase_replanning=True,
        enable_local_recovery=False,
        local_recovery_max_cycles=0,
    ),
    "full": RecoverySettings(
        mode="full",
        max_phases=3,
        enable_phase_replanning=True,
        enable_local_recovery=True,
        local_recovery_max_cycles=1,
    ),
}


def get_recovery_settings(mode: str) -> RecoverySettings:
    try:
        return MODES[mode]
    except KeyError as exc:
        allowed = ", ".join(MODES)
        raise ValueError(
            f"unknown recovery mode {mode!r}; expected one of: {allowed}"
        ) from exc


def build_replanner(mode: str, replanner: Any):
    settings = get_recovery_settings(mode)

    if not settings.enable_phase_replanning:
        return None

    if replanner is None:
        raise ValueError(
            f"recovery mode {mode!r} requires a replanner"
        )

    return replanner


def build_local_recovery(mode: str, orchestrator: Any):
    settings = get_recovery_settings(mode)

    if not settings.enable_local_recovery:
        return None

    return LocalDAGRecoveryController(
        orchestrator,
        max_cycles=settings.local_recovery_max_cycles,
    )
