"""backfill: daily at 03:40 MYT. Refill missed 15-min samples and trim raw payloads (architecture §6.3)."""
from __future__ import annotations

import argparse
import sys

from .. import config, db
from ..runlog import RunLog
from ..sources import openmeteo
from ..timeutil import utcnow
from ._common import base_parser, run, write

STEPS = ("om_gapfill", "retention")
HOT_TABLES = ("observations", "forecasts", "forecasts_daily", "satellite_features", "predictions",
              "ingestion_runs", "raw_responses")


def body(log: RunLog, args: argparse.Namespace) -> None:
    steps = args.steps.split(",") if args.steps else STEPS

    if "om_gapfill" in steps:
        with log.step("om_gapfill") as step:
            rows = openmeteo.parse_minutely15(openmeteo.fetch_minutely15(args.days), utcnow())
            # Fill holes only after the first live sample, so backfill can never stretch the
            # "continuous collection" streak back before the data clock started.
            if log.conn is not None:
                first_live = db.scalar(log.conn, """select min(observed_at) from observations
                    where source = 'openmeteo_current' and not is_backfill and location_id = %s""",
                    (config.LOCATION_ID,))
                rows = [r for r in rows if first_live is not None and r["observed_at"] > first_live]
                step["note"] = f"after first live sample {first_live}"
            # Only missing samples are inserted; values already collected live are never overwritten.
            write(log, "observations", rows, ("location_id", "source", "observed_at"), "nothing")

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
    p.add_argument("--steps", help=f"comma-separated subset of {','.join(STEPS)}")
    return p


def main(argv: list[str] | None = None) -> int:
    return run("backfill", parser(), body, argv)


if __name__ == "__main__":
    sys.exit(main())
