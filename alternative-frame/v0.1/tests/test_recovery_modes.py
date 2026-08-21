import pytest

from core.evaluation.recovery_modes import (
    build_local_recovery,
    build_replanner,
    get_recovery_settings,
)
from core.local_recovery import LocalDAGRecoveryController


class FakeOrchestrator:
    pass


class FakeReplanner:
    pass


def test_none_mode_disables_both_recovery_layers():
    settings = get_recovery_settings("none")

    assert settings.max_phases == 1
    assert settings.enable_phase_replanning is False
    assert settings.enable_local_recovery is False

    replanner = FakeReplanner()

    assert build_replanner("none", replanner) is None
    assert build_local_recovery("none", FakeOrchestrator()) is None


def test_phase_mode_only_enables_phase_replanning():
    settings = get_recovery_settings("phase")

    assert settings.max_phases == 3
    assert settings.enable_phase_replanning is True
    assert settings.enable_local_recovery is False

    replanner = FakeReplanner()

    assert build_replanner("phase", replanner) is replanner
    assert build_local_recovery("phase", FakeOrchestrator()) is None


def test_full_mode_enables_both_recovery_layers():
    settings = get_recovery_settings("full")
    orchestrator = FakeOrchestrator()
    replanner = FakeReplanner()

    assert settings.max_phases == 3
    assert settings.enable_phase_replanning is True
    assert settings.enable_local_recovery is True

    assert build_replanner("full", replanner) is replanner

    local = build_local_recovery("full", orchestrator)

    assert isinstance(local, LocalDAGRecoveryController)
    assert local.orchestrator is orchestrator
    assert local.max_cycles == 1


def test_unknown_mode_is_rejected():
    with pytest.raises(ValueError):
        get_recovery_settings("magic")


def test_phase_and_full_require_replanner():
    with pytest.raises(ValueError):
        build_replanner("phase", None)

    with pytest.raises(ValueError):
        build_replanner("full", None)
