from mobiflow_agent.common.ids import build_suite_run_id


def test_build_suite_run_id_has_prefix_and_is_unique() -> None:
    first = build_suite_run_id()
    second = build_suite_run_id()

    assert first.startswith("suite-run:")
    assert len(first) > len("suite-run:")
    assert first != second
