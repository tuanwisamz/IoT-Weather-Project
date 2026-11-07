from datetime import date, datetime, timezone

from iww_ingest.sources import openmeteo
from iww_ingest.timeutil import om_local_to_utc

UTC = timezone.utc
MODELS = ["best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless"]


def test_current_row_is_utc_interval_end(fixture):
    js = fixture("om_current.json")
    row = openmeteo.parse_current(js)
    assert row["observed_at"] == datetime.fromisoformat(js["current"]["time"]).replace(tzinfo=UTC)
    assert row["interval_min"] == 15
    assert row["source"] == "openmeteo_current"
    assert isinstance(row["weather_code"], int)
    assert row["temperature_c"] == js["current"]["temperature_2m"]
    assert row["raw"] == js["current"]


def test_local_times_shift_to_utc():
    assert om_local_to_utc("2026-10-31T00:00", 28800) == datetime(2026, 10, 30, 16, tzinfo=UTC)


def test_multi_model_vault_unpacks_suffixed_keys(fixture):
    js = fixture("om_forecast_multi.json")
    issued = datetime(2026, 10, 31, 6, tzinfo=UTC)
    runs = {"ecmwf_ifs025": datetime(2026, 10, 30, 18, tzinfo=UTC)}
    hourly, daily = openmeteo.parse_forecast(js, MODELS, issued, runs)
    per_model = {m: [r for r in hourly if r["model"] == m] for m in MODELS}
    assert all(len(rows) > 100 for rows in per_model.values())
    assert all(r["target_time"] >= issued for r in hourly)
    first = per_model["gfs_seamless"][0]
    i = js["hourly"]["time"].index("2026-10-31T14:00")          # 06:00 UTC in MYT
    assert first["target_time"] == issued
    assert first["temperature_c"] == js["hourly"]["temperature_2m_gfs_seamless"][i]
    assert per_model["ecmwf_ifs025"][0]["model_run_at"] == runs["ecmwf_ifs025"]
    assert per_model["best_match"][0]["model_run_at"] is None
    # best_match must not pick up another model's values through a shared prefix
    assert per_model["best_match"][0]["temperature_c"] == js["hourly"]["temperature_2m_best_match"][i]
    assert {r["lead_days"] for r in daily} == set(range(7))
    assert len(daily) == 7 * len(MODELS)


def test_single_model_uses_bare_keys(fixture):
    js = fixture("om_forecast_single.json")
    issued = om_local_to_utc(js["hourly"]["time"][0], js["utc_offset_seconds"])
    hourly, daily = openmeteo.parse_forecast(js, ["best_match"], issued, {})
    assert len(hourly) == len(js["hourly"]["time"])
    assert hourly[0]["temperature_c"] == js["hourly"]["temperature_2m"][0]
    assert daily[0]["target_date"] == date.fromisoformat(js["daily"]["time"][0])
    assert daily[0]["temp_max_c"] == js["daily"]["temperature_2m_max"][0]


def test_hours_before_issue_are_dropped(fixture):
    js = fixture("om_forecast_single.json")
    issued = om_local_to_utc(js["hourly"]["time"][10], js["utc_offset_seconds"])
    hourly, _ = openmeteo.parse_forecast(js, ["best_match"], issued, {})
    assert len(hourly) == len(js["hourly"]["time"]) - 10
    assert min(r["target_time"] for r in hourly) == issued


def test_daily_lead_days_follow_local_dates(fixture):
    js = fixture("om_forecast_single.json")
    # 17:30 UTC on 30 Oct is already 31 Oct in MYT, so 31 Oct is lead 0.
    _, daily = openmeteo.parse_forecast(js, ["best_match"], datetime(2026, 10, 30, 17, tzinfo=UTC), {})
    by_date = {r["target_date"]: r["lead_days"] for r in daily}
    assert by_date[date(2026, 10, 31)] == 0


def test_gapfill_never_writes_the_future(fixture):
    js = fixture("om_minutely15.json")
    now = datetime(2026, 10, 30, 12, 7, tzinfo=UTC)
    rows = openmeteo.parse_minutely15(js, now)
    assert rows and max(r["observed_at"] for r in rows) == datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
    assert all(r["is_backfill"] and r["interval_min"] == 15 for r in rows)
    assert rows[0]["observed_at"] == datetime(2026, 10, 29, 0, 0, tzinfo=UTC)
