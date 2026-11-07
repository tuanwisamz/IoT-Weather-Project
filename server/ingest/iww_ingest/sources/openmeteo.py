"""Open-Meteo: current analysis, the forecast vault, model run metadata and 15-min gap fill (api-spec §5.1–5.3)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .. import config, http
from ..timeutil import from_unix, myt_date, om_local_to_utc

BASE = {"latitude": config.LAT, "longitude": config.LON}
SOURCE = "openmeteo_current"


def _num(value: Any, integer: bool = False) -> Any:
    if value is None:
        return None
    return int(round(value)) if integer else float(value)


# --- current ----------------------------------------------------------------------------------

def fetch_current() -> dict:
    data, _, _ = http.get_json(config.OM_FORECAST_URL,
                               {**BASE, "current": ",".join(config.CURRENT_REQUEST), "timezone": "GMT"})
    return data


def parse_current(js: dict) -> dict:
    cur = js["current"]
    row = {
        "location_id": config.LOCATION_ID,
        "source": SOURCE,
        "observed_at": om_local_to_utc(cur["time"], js.get("utc_offset_seconds", 0)),   # END of the interval
        "interval_min": int(cur.get("interval", 900)) // 60,
    }
    for om, col in config.CURRENT_VARS.items():
        row[col] = _num(cur.get(om), integer=(col == "weather_code"))
    row["raw"] = cur
    return row


# --- forecast vault ---------------------------------------------------------------------------

def fetch_forecast(models: list[str]) -> tuple[dict, int, str]:
    return http.get_json(config.OM_FORECAST_URL, {
        **BASE,
        "models": ",".join(models),
        "hourly": ",".join(config.HOURLY_VARS),
        "daily": ",".join(config.DAILY_VARS),
        "forecast_days": config.FORECAST_DAYS,
        "timezone": config.LOCAL_TZ,
    })


def _series(block: dict, var: str, model: str, n_models: int) -> list | None:
    """Multi-model responses suffix every key with the model (✔ incl. best_match); single-model ones don't."""
    if n_models > 1 and f"{var}_{model}" in block:
        return block[f"{var}_{model}"]
    return block.get(var) if n_models == 1 else None


def parse_forecast(js: dict, models: list[str], issued_at: datetime,
                   run_times: dict[str, datetime | None]) -> tuple[list[dict], list[dict]]:
    offset = js["utc_offset_seconds"]
    hourly, daily = js.get("hourly", {}), js.get("daily", {})
    times = [om_local_to_utc(t, offset) for t in hourly.get("time", [])]
    days = [date.fromisoformat(t) for t in daily.get("time", [])]
    issued_day = myt_date(issued_at)
    hourly_rows: list[dict] = []
    daily_rows: list[dict] = []
    for model in models:
        cols = {col: _series(hourly, om, model, len(models)) for om, col in config.HOURLY_VARS.items()}
        for i, target in enumerate(times):
            if target < issued_at:
                continue
            values = {col: _num(s[i], integer=(col == "weather_code")) if s else None for col, s in cols.items()}
            if all(v is None for v in values.values()):
                continue                                    # beyond this model's horizon
            hourly_rows.append({
                "location_id": config.LOCATION_ID, "model": model, "origin": "snapshot",
                "issued_at": issued_at, "model_run_at": run_times.get(model), "target_time": target, **values,
            })
        dcols = {col: _series(daily, om, model, len(models)) for om, col in config.DAILY_VARS.items()}
        for i, day in enumerate(days):
            values = {col: _num(s[i]) if s else None for col, s in dcols.items()}
            if all(v is None for v in values.values()):
                continue
            daily_rows.append({
                "location_id": config.LOCATION_ID, "model": model, "issued_at": issued_at,
                "target_date": day, "lead_days": (day - issued_day).days, **values,
            })
    return hourly_rows, daily_rows


# --- model run metadata -----------------------------------------------------------------------

def fetch_run_time(meta_key: str) -> datetime:
    data, _, _ = http.get_json(config.OM_META_URL.format(meta_key=meta_key))
    return from_unix(data["last_run_initialisation_time"])


# --- 15-min gap fill (backfill) ---------------------------------------------------------------

def fetch_minutely15(past_days: int) -> dict:
    data, _, _ = http.get_json(config.OM_FORECAST_URL, {
        **BASE,
        "minutely_15": ",".join(config.CURRENT_VARS),
        "past_days": past_days,
        "forecast_days": 1,
        "timezone": "GMT",
    })
    return data


def parse_minutely15(js: dict, now: datetime) -> list[dict]:
    block = js["minutely_15"]
    offset = js.get("utc_offset_seconds", 0)
    rows = []
    for i, t in enumerate(block["time"]):
        observed_at = om_local_to_utc(t, offset)
        if observed_at > now:
            break
        sample = {om: block[om][i] for om in config.CURRENT_VARS if om in block}
        if all(v is None for v in sample.values()):
            continue
        row = {"location_id": config.LOCATION_ID, "source": SOURCE, "observed_at": observed_at,
               "interval_min": 15, "is_backfill": True}
        for om, col in config.CURRENT_VARS.items():
            row[col] = _num(sample.get(om), integer=(col == "weather_code"))
        row["raw"] = {"time": t, **sample}
        rows.append(row)
    return rows
