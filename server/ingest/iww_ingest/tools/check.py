"""Daily sanity check: row counts, the last run per job, and the collection streak (tasks.md T3.6).

    python -m iww_ingest.tools.check --window 2026-11-04,2026-11-07

--window runs the data check that freezes the report window (Implementation-plan §5.3). It prints
counts only, so the window is chosen without seeing any accuracy score.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from math import ceil

from .. import config, db
from ..timeutil import myt_midnight

TABLES = ("observations", "forecasts", "forecasts_daily", "satellite_features", "predictions",
          "ingestion_runs", "raw_responses")


MIN_COMPLETE_SHARE = 0.9     # 65 of 72 hours
MIN_RAIN_HOURS = 6
MIN_DAY1_PAIRS = 60          # per 72 hours of window
CHECK_MODELS = ("best_match", "ecmwf_ifs025", "gfs_seamless", "icon_seamless")


def window_check(conn, first: date, last: date) -> bool:
    since, until = myt_midnight(first), myt_midnight(last)
    expected = int((until - since).total_seconds() // 3600)
    complete, rain = db.fetch_all(conn, """
        select count(*), count(*) filter (where rain_hour) from v_actual_hourly
        where source = 'openmeteo_current' and samples = 4 and hour >= %s and hour < %s""", (since, until))[0]
    pairs = dict(db.fetch_all(conn, """
        select model, count(*) from v_pairs
        where truth_source = 'openmeteo_current' and variable = 'temperature_c' and lead_hours = 24
          and target_time >= %s and target_time < %s group by model""", (since, until)))
    min_complete = ceil(expected * MIN_COMPLETE_SHARE)
    min_pairs = MIN_DAY1_PAIRS * expected // 72
    checks = [(f"complete hours {complete} of {expected} (need {min_complete})", complete >= min_complete),
              (f"rain hours {rain} (need {MIN_RAIN_HOURS})", rain >= MIN_RAIN_HOURS)]
    checks += [(f"day-1 pairs {m} {pairs.get(m, 0)} (need {min_pairs})", pairs.get(m, 0) >= min_pairs)
               for m in CHECK_MODELS]
    print(f"Data check {first} to {last} (MYT)")
    for label, ok in checks:
        print(f"  {'pass' if ok else 'FAIL'}  {label}")
    passed = all(ok for _, ok in checks)
    print(f"Result: {'PASS' if passed else 'FAIL'}")
    return passed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m iww_ingest.tools.check")
    p.add_argument("--window", help="FROM,TO local MYT dates: print the data check instead")
    args = p.parse_args(argv)
    cfg = config.settings()
    if not cfg.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 1
    with db.connect(cfg.db_url, "check") as conn:
        if args.window:
            first, last = map(date.fromisoformat, args.window.split(","))
            return 0 if window_check(conn, first, last) else 1

        print("Rows per table")
        for table in TABLES:
            print(f"  {table:<20} {db.scalar(conn, f'select count(*) from {table}'):>9,}")

        print("\nObservations per source (newest)")
        for source, n, newest in db.fetch_all(conn, """select source, count(*), max(observed_at)
                                                       from observations group by source order by source"""):
            print(f"  {source:<22} {n:>7,}  {newest:%Y-%m-%d %H:%M} UTC")

        print("\nLast run per job")
        for job, status, started, steps in db.fetch_all(conn, """
                select distinct on (job) job, status, started_at, steps from ingestion_runs
                order by job, started_at desc"""):
            failed = [s["step"] for s in steps if not s.get("ok")]
            print(f"  {job:<9} {status:<8} {started:%Y-%m-%d %H:%M} UTC" + (f"  failed: {failed}" if failed else ""))

        has_view = db.scalar(conn, "select to_regclass('public.v_collection_window') is not null")
        if has_view:
            row = db.fetch_all(conn, "select streak_start, streak_hours, samples, expected_samples, meets_3_days "
                                     "from v_collection_window")
            if row:
                start, hours, samples, expected, ok = row[0]
                print(f"\nStreak: {hours:.1f} h since {start:%Y-%m-%d %H:%M} UTC, "
                      f"{samples}/{expected} samples, meets 3 days: {ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
