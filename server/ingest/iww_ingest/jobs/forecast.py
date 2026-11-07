"""forecast: hourly. Store each model run once in the forecast vault (architecture §6.2)."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime

from psycopg.types.json import Jsonb

from .. import config, db
from ..runlog import RunLog
from ..sources import openmeteo
from ..timeutil import floor_to, utcnow
from ._common import base_parser, run, write

log = logging.getLogger(__name__)
HOURLY_KEY = ("location_id", "model", "origin", "issued_at", "target_time")
DAILY_KEY = ("location_id", "model", "issued_at", "target_date")


def active_models(runlog: RunLog) -> dict[str, str | None]:
    """code → meta_key for active models (the seed list when there's no database)."""
    if runlog.conn is None:
        return dict(config.DEFAULT_MODELS)
    rows = db.fetch_all(runlog.conn, "select code, meta_key from forecast_models where is_active order by code")
    return dict(rows)


def latest_run_at(runlog: RunLog, model: str) -> datetime | None:
    if runlog.conn is None:
        return None
    return db.scalar(runlog.conn, "select max(model_run_at) from forecasts where model = %s and origin = 'snapshot'",
                     (model,))


def body(runlog: RunLog, args: argparse.Namespace) -> None:
    issued_at = floor_to(utcnow(), 60)
    models = active_models(runlog)
    if args.models:
        models = {m: models.get(m) for m in args.models.split(",")}
    run_times: dict[str, datetime | None] = dict.fromkeys(models)
    due = list(models)                                    # if model_runs fails, store everything

    with runlog.step("model_runs") as step:
        checked, notes = [], []
        for model, meta_key in models.items():
            if meta_key is None:                          # best_match blends hourly: always due
                checked.append(model)
                continue
            try:
                run_times[model] = openmeteo.fetch_run_time(meta_key)
            except Exception as exc:  # noqa: BLE001: fall back to storing it every hour
                log.warning("meta.json for %s failed (%s); storing it hourly", model, exc)
                notes.append(f"{model}: meta failed, stored hourly")
                checked.append(model)
                continue
            stored = latest_run_at(runlog, model)
            if args.force or stored is None or run_times[model] > stored:
                checked.append(model)
        due = checked
        step["note"] = f"due: {','.join(due) or 'none'}" + (f"; {'; '.join(notes)}" if notes else "")

    if not due:
        return
    with runlog.step("vault"):
        js, status, url = openmeteo.fetch_forecast(due)
        hourly, daily = openmeteo.parse_forecast(js, due, issued_at, run_times)
        if not hourly:
            raise ValueError("forecast response contained no hourly rows")
        write(runlog, "forecasts", hourly, HOURLY_KEY, "nothing")       # issued_at = first obtained
        write(runlog, "forecasts_daily", daily, DAILY_KEY, "nothing")
        if runlog.writing:
            with runlog.conn.cursor() as cur:
                cur.execute("insert into raw_responses (run_id, source, url, http_status, payload) "
                            "values (%s, 'openmeteo_forecast', %s, %s, %s)", (runlog.run_id, url, status, Jsonb(js)))
            runlog.rows("raw_responses", 1)


def parser() -> argparse.ArgumentParser:
    p = base_parser("forecast")
    p.add_argument("--models", help="comma-separated subset of the active models")
    p.add_argument("--force", action="store_true", help="store a snapshot even if the model isn't due")
    return p


def main(argv: list[str] | None = None) -> int:
    return run("forecast", parser(), body, argv)


if __name__ == "__main__":
    sys.exit(main())
