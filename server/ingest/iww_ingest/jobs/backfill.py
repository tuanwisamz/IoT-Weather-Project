"""backfill: daily at 03:40 MYT. Refill missed 15-min samples and trim raw payloads (architecture §6.3).

With --since and --until it's the one-off import of past data instead (Implementation-plan §5.3):

    python -m iww_ingest.jobs.backfill --since 2026-11-01 --until 2026-11-07 --steps om_gapfill,metar_history,previous_runs
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import date, datetime, timedelta

from psycopg.types.json import Jsonb

from .. import config, db
from ..runlog import RunLog
from ..sources import metar, openmeteo
from ..timeutil import myt_midnight, utcnow
from ._common import base_parser, run, write
from .forecast import HOURLY_KEY, active_models
from .observe import OBS_KEY

STEPS = ("om_gapfill", "retention")
IMPORT_STEPS = ("om_gapfill", "metar_history", "previous_runs")
HOT_TABLES = ("observations", "forecasts", "forecasts_daily", "satellite_features", "predictions",
              "ingestion_runs", "raw_responses")


def import_range(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """--since/--until as UTC instants."""
    if not args.since or not args.until:
        raise ValueError("this step needs --since and --until")
    return myt_midnight(args.since), myt_midnight(args.until)


def body(log: RunLog, args: argparse.Namespace) -> None:
    steps = args.steps.split(",") if args.steps else STEPS

    if "om_gapfill" in steps:
        with log.step("om_gapfill") as step:
            if args.since:
                since, until = import_range(args)
                past_days = (utcnow() - since).days + 2
                rows = openmeteo.parse_minutely15(openmeteo.fetch_minutely15(past_days), utcnow())
                # Hour H covers (H-1h, H], so the first hour needs samples from just before --since.
                rows = [r for r in rows if since - timedelta(hours=1) < r["observed_at"] <= until]
                step["note"] = f"import {since:%Y-%m-%d %H:%M} to {until:%Y-%m-%d %H:%M} UTC"
            else:
                rows = openmeteo.parse_minutely15(openmeteo.fetch_minutely15(args.days), utcnow())
                # The daily run only fills holes after the first live sample, so it can never pass
                # retrieved data off as live collection.
                if log.conn is not None:
                    first_live = db.scalar(log.conn, """select min(observed_at) from observations
                        where source = 'openmeteo_current' and not is_backfill and location_id = %s""",
                        (config.LOCATION_ID,))
                    rows = [r for r in rows if first_live is not None and r["observed_at"] > first_live]
                    step["note"] = f"after first live sample {first_live}"
            # Only missing samples are inserted; values already collected live are never overwritten.
            write(log, "observations", rows, OBS_KEY, "nothing")

    if "metar_history" in steps:
        with log.step("metar_history"):
            since, until = import_range(args)
            hours = math.ceil((utcnow() - since).total_seconds() / 3600) + 1
            rows = [{**r, "is_backfill": True} for r in metar.parse(metar.fetch(hours=hours))
                    if since <= r["observed_at"] < until]
            write(log, "observations", rows, OBS_KEY, "update")

    if "previous_runs" in steps:
        with log.step("previous_runs"):
            since, until = import_range(args)
            models = list(active_models(log))
            js, status, url = openmeteo.fetch_previous_runs(models, since.date(), until.date())   # GMT dates
            rows = openmeteo.parse_previous_runs(js, models, since, until)
            if not rows:
                raise ValueError("Previous Runs response contained no rows")
            write(log, "forecasts", rows, HOURLY_KEY, "nothing")
            if log.writing:
                with log.conn.cursor() as cur:
                    cur.execute("insert into raw_responses (run_id, source, url, http_status, payload) "
                                "values (%s, 'openmeteo_previous_runs', %s, %s, %s)",
                                (log.run_id, url, status, Jsonb(js)))
                log.rows("raw_responses", 1)

    if "retention" in steps:
        with log.step("retention", transactional=False):
            if log.writing:
                with log.conn.cursor() as cur:
                    cur.execute("delete from raw_responses where fetched_at < now() - make_interval(days => %s)",
                                (config.RAW_RETENTION_DAYS,))
                    log.rows("raw_responses_deleted", cur.rowcount)
                    for table in HOT_TABLES:
                        cur.execute(f"vacuum (analyze) {table}")


def parser() -> argparse.ArgumentParser:
    p = base_parser("backfill")
    p.add_argument("--days", type=int, default=2, help="how many past days to gap-fill")
    p.add_argument("--steps", help=f"comma-separated subset of {','.join(STEPS + IMPORT_STEPS[1:])}")
    p.add_argument("--since", type=date.fromisoformat, help="import start, local MYT date")
    p.add_argument("--until", type=date.fromisoformat, help="import end (exclusive), local MYT date")
    return p


def main(argv: list[str] | None = None) -> int:
    return run("backfill", parser(), body, argv)


if __name__ == "__main__":
    sys.exit(main())
