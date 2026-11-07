"""Shared job plumbing: CLI flags, logging, the DB connection and dry-run aware writes (api-spec §6)."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .. import config, db
from ..runlog import RunLog, exit_code

log = logging.getLogger("iww")


def base_parser(job: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"python -m iww_ingest.jobs.{job}")
    p.add_argument("--dry-run", action="store_true", help="fetch and parse, write nothing")
    p.add_argument("--trigger", choices=["schedule", "dispatch", "local"], default=config.default_trigger())
    return p


def run(job: str, parser: argparse.ArgumentParser, body: Callable[[RunLog, argparse.Namespace], None],
        argv: Sequence[str] | None = None) -> int:
    args = parser.parse_args(argv)
    cfg = config.settings()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        stream=sys.stdout)
    if not cfg.db_url and not args.dry_run:
        log.error("SUPABASE_DB_URL is not set (use --dry-run to test without a database)")
        return 1
    conn = None
    if cfg.db_url:
        try:
            conn = db.connect(cfg.db_url, job)
        except Exception as exc:  # noqa: BLE001
            log.error("cannot connect to the database: %s", exc)
            if not args.dry_run:
                return 1
    try:
        runlog = RunLog(job, args.trigger, conn, cfg.gh_run_id, args.dry_run).start()
        body(runlog, args)
        return exit_code(runlog.finish())
    finally:
        if conn is not None:
            conn.close()


def write(runlog: RunLog, table: str, rows: list[Mapping[str, Any]], key: Sequence[str],
          on_conflict: str = "nothing") -> int:
    """Upsert when writing; otherwise count the rows and print one sample."""
    if runlog.writing:
        n = db.upsert(runlog.conn, table, [{**r, "run_id": runlog.run_id} for r in rows], key, on_conflict)
    else:
        n = len(rows)
        if rows:
            print(f"--- {table}: {n} rows, first:\n{preview(rows[0])}")
    runlog.rows(table, n)
    return n


def preview(row: Mapping[str, Any]) -> str:
    shown = {k: (v if k != "raw" else "<raw>") for k, v in row.items()}
    return json.dumps(shown, default=str, indent=1)
