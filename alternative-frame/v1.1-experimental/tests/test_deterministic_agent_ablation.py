from run_deterministic_agent_ablation import run_once


def test_single_agent_uses_one_shared_backend():
    result = run_once(
        "single_agent",
        0.01,
    )

    assert result.goal_completed is True
    assert result.success_count == 5
    assert result.first_pass_count == 5

    assert result.logical_role_count == 5
    assert result.unique_backend_count == 1

    assert result.handoff_count == 0

    # Shared backend serializes the two independent tasks.
    assert result.parallel_overlap_seconds < 0.005


def test_multi_agent_uses_role_specific_backends():
    result = run_once(
        "multi_agent",
        0.03,
    )

    assert result.goal_completed is True
    assert result.success_count == 5
    assert result.first_pass_count == 5

    assert result.logical_role_count == 5
    assert result.unique_backend_count == 5

    assert result.handoff_count >= 3

    # Architecture and implementation should overlap.
    assert result.parallel_overlap_seconds > 0.01


def test_multi_agent_preserves_same_task_outcome():
    single = run_once(
        "single_agent",
        0.02,
    )

    multi = run_once(
        "multi_agent",
        0.02,
    )

    assert single.goal_completed is True
    assert multi.goal_completed is True

    assert (
        single.task_count
        == multi.task_count
        == 5
    )

    assert (
        single.success_count
        == multi.success_count
        == 5
    )

    assert (
        single.first_pass_count
        == multi.first_pass_count
        == 5
    )


def test_multi_agent_parallelism_reduces_wall_clock_time():
    # Use a sufficiently large deterministic delay so
    # scheduler noise does not dominate the comparison.
    single = run_once(
        "single_agent",
        0.05,
    )

    multi = run_once(
        "multi_agent",
        0.05,
    )

    assert (
        multi.duration_seconds
        < single.duration_seconds
    )
