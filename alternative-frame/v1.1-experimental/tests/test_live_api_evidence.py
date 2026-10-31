from run_real_two_phase_demo import aggregate_model_usage


def test_aggregate_usage_sums_provider_counts_and_unknown_calls():
    records = [
        {"call_type": "model_call", "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13}},
        {"call_type": "model_call", "usage": {"input_tokens": 20, "output_tokens": 5}},
        {"call_type": "tool_call", "usage": {"prompt_tokens": 999}},
    ]
    assert aggregate_model_usage(records) == (2, "reported", 30, 8, 38)


def test_usage_is_unknown_if_any_model_response_omits_counts():
    records = [
        {"call_type": "model_call", "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
        {"call_type": "model_call", "usage": None},
    ]
    assert aggregate_model_usage(records) == (2, "unknown", None, None, None)


def test_no_model_usage_is_unknown_not_zero():
    assert aggregate_model_usage([]) == (0, "unknown", None, None, None)
