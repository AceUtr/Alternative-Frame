from run_deterministic_recovery_ablation import run_mode


def test_without_recovery_deterministic_failure_remains_failed():
    result = run_mode("recovery_off")

    assert result.goal_completed is False
    assert result.status == "failed"

    assert result.local_recovery_count == 0

    assert result.prepare_attempts == 1
    assert result.compute_attempts == 1
    assert result.verify_attempts == 0

    assert result.execution_log == [
        "prepare",
        "compute",
    ]


def test_local_recovery_recovers_only_impacted_subgraph():
    result = run_mode("recovery_on")

    assert result.goal_completed is True
    assert result.status == "success"

    assert result.local_recovery_count == 1

    # prepare succeeded before the failure and is frozen.
    assert result.prepare_attempts == 1
    assert result.frozen_prepare is True

    # compute failed once and succeeded during local recovery.
    assert result.compute_attempts == 2

    # verify was originally blocked and only runs in recovery.
    assert result.verify_attempts == 1

    assert result.execution_log == [
        "prepare",
        "compute",
        "compute",
        "verify",
    ]


def test_recovery_adds_only_required_execution_work():
    off = run_mode("recovery_off")
    on = run_mode("recovery_on")

    assert off.goal_completed is False
    assert on.goal_completed is True

    assert off.local_recovery_count == 0
    assert on.local_recovery_count == 1

    # Most important locality invariant:
    # the successful predecessor is not rerun.
    assert on.prepare_attempts == 1

    # Four executions total:
    # prepare + failed compute + recovered compute + verify.
    assert len(on.execution_log) == 4
