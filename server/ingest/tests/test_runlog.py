import pytest

from iww_ingest.runlog import RunLog, exit_code


def run_steps(*outcomes):
    log = RunLog("observe", "local", dry_run=True).start()
    for i, ok in enumerate(outcomes):
        with log.step(f"s{i}"):
            log.rows("observations", 1)
            if not ok:
                raise RuntimeError("boom")
    return log


def test_all_ok_is_success():
    log = run_steps(True, True)
    assert log.finish() == "success" and exit_code("success") == 0
    assert log.rows_written["observations"] == 2


def test_one_failure_is_partial_and_its_rows_dont_count():
    log = run_steps(True, False)
    assert log.finish() == "partial" and exit_code("partial") == 0
    assert log.rows_written["observations"] == 1
    assert log.steps[1]["ok"] is False and "boom" in log.steps[1]["error"]


def test_all_failed_is_failed_and_exits_1():
    log = run_steps(False, False)
    assert log.finish() == "failed" and exit_code("failed") == 1


def test_rows_outside_a_step_is_a_bug():
    with pytest.raises(RuntimeError):
        RunLog("observe", "local", dry_run=True).rows("observations", 1)
