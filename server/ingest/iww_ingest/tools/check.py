"""Daily sanity check: row counts, the last run per job, and the collection streak (tasks.md T3.6)."""
from __future__ import annotations

import sys

from .. import config, db

TABLES = ("observations", "forecasts", "forecasts_daily", "satellite_features", "predictions",
          "ingestion_runs", "raw_responses")


def main() -> int:
    cfg = config.settings()
    if not cfg.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 1
    with db.connect(cfg.db_url, "check") as conn:
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
