from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone

from iww_ingest import config
from iww_ingest.jobs import backfill
from iww_ingest.sources import metar, openmeteo
from iww_ingest.timeutil import myt_midnight

UTC = timezone.utc
MODELS = ["best_match", "icon_seamless"]
TIMES = ["2026-11-03T15:00", "2026-11-03T16:00", "2026-11-03T17:00", "2026-11-06T16:00"]
SINCE, UNTIL = myt_midnight(date(2026, 11, 4)), myt_midnight(date(2026, 11, 7))
IMPORT = ["--since", "2026-11-04", "--until", "2026-11-07", "--steps"]


def response() -> dict:
    hourly = {"time": TIMES}
    for model in MODELS:
        for om in config.PREVIOUS_RUNS_VARS:
            for n in config.PREVIOUS_RUNS_DAYS:
                hourly[f"{om}_previous_day{n}_{model}"] = [20.0 + n] * len(TIMES)
    hourly |= {f"{om}_previous_day7_icon_seamless": [None] * len(TIMES) for om in config.PREVIOUS_RUNS_VARS}
    return {"utc_offset_seconds": 0, "hourly": hourly}


def test_issued_at_is_target_minus_n_days():
    rows = openmeteo.parse_previous_runs(response(), MODELS, SINCE, UNTIL)
    day3 = next(r for r in rows if r["model"] == "best_match" and r["issued_at"] == SINCE - timedelta(days=3))
    assert day3["target_time"] == SINCE
    assert day3["temperature_c"] == 23.0
    assert day3["origin"] == "previous_runs"


def test_range_is_since_inclusive_until_exclusive():
    rows = openmeteo.parse_previous_runs(response(), MODELS, SINCE, UNTIL)
    assert {r["target_time"] for r in rows} == {SINCE, datetime(2026, 11, 3, 17, tzinfo=UTC)}


def test_null_columns_are_skipped_so_icon_has_no_day_7():
    rows = openmeteo.parse_previous_runs(response(), MODELS, SINCE, UNTIL)

    def leads(model):
        return {(r["target_time"] - r["issued_at"]).days for r in rows if r["model"] == model}

    assert leads("best_match") == set(range(1, 8))
    assert leads("icon_seamless") == set(range(1, 7))


def test_rain_probability_is_never_requested():
    assert "precipitation_probability" not in config.PREVIOUS_RUNS_VARS


def test_myt_midnight_is_previous_day_16_utc():
    assert SINCE == datetime(2026, 11, 3, 16, tzinfo=UTC)


class FakeLog:
    conn = None
    writing = False

    def step(self, name, transactional=True):
        return nullcontext({})


def test_metar_history_keeps_range_and_marks_backfill(monkeypatch):
    inside = int(SINCE.timestamp()) + 3600
    reports = [{"obsTime": t, "temp": 30, "dewp": 25, "wspd": 5}
               for t in (inside, int(UNTIL.timestamp()), int(SINCE.timestamp()) - 3600)]
    seen = {}
    monkeypatch.setattr(metar, "fetch", lambda hours: seen.update(hours=hours) or reports)
    monkeypatch.setattr(backfill, "write", lambda log, table, rows, key, mode="nothing": seen.update(rows=rows))
    backfill.body(FakeLog(), backfill.parser().parse_args(IMPORT + ["metar_history"]))
    assert [r["observed_at"].timestamp() for r in seen["rows"]] == [inside]
    assert seen["rows"][0]["is_backfill"] is True
    assert seen["hours"] > 72


def test_import_gapfill_starts_an_hour_early_and_stops_at_until(monkeypatch):
    edge = [SINCE - timedelta(minutes=45), SINCE - timedelta(hours=1), UNTIL, UNTIL + timedelta(minutes=15)]
    seen = {}
    monkeypatch.setattr(openmeteo, "fetch_minutely15", lambda days: seen.update(days=days) or {})
    monkeypatch.setattr(openmeteo, "parse_minutely15",
                        lambda js, now: [{"location_id": 1, "observed_at": t} for t in edge])
    monkeypatch.setattr(backfill, "write", lambda log, table, rows, key, mode="nothing": seen.update(rows=rows))
    backfill.body(FakeLog(), backfill.parser().parse_args(IMPORT + ["om_gapfill"]))
    assert [r["observed_at"] for r in seen["rows"]] == [edge[0], UNTIL]
    assert seen["days"] >= 3


def test_previous_runs_requests_utc_dates_covering_the_first_myt_hours(monkeypatch):
    seen = {}

    def fetch(models, start, end):
        seen.update(start=start, end=end)
        return {"hourly": {}}, 200, "url"

    monkeypatch.setattr(openmeteo, "fetch_previous_runs", fetch)
    monkeypatch.setattr(backfill, "active_models", lambda log: {"best_match": None})
    log = FakeLog()
    log.step = lambda name, transactional=True: _Swallow()
    backfill.body(log, backfill.parser().parse_args(IMPORT + ["previous_runs"]))
    assert seen == {"start": date(2026, 11, 3), "end": date(2026, 11, 6)}


class _Swallow:
    def __enter__(self):
        return {}

    def __exit__(self, *exc):
        return True
