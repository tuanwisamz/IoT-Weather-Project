"""`ingestion_runs` lifecycle: start, independent steps, finish (architecture §6)."""
from __future__ import annotations

import json
import logging
import time
from collections import Counter
from contextlib import contextmanager, nullcontext
from typing import Iterator

import psycopg
from psycopg.types.json import Jsonb

log = logging.getLogger(__name__)


class RunLog:
    def __init__(self, job: str, trigger: str, conn: psycopg.Connection | None = None,
                 gh_run_id: int | None = None, dry_run: bool = False):
        self.job, self.trigger, self.gh_run_id = job, trigger, gh_run_id
        self.conn, self.dry_run = conn, dry_run
        self.run_id: int | None = None
        self.steps: list[dict] = []
        self.rows_written: Counter[str] = Counter()
        self._step_rows: Counter[str] | None = None

    @property
    def writing(self) -> bool:
        return self.conn is not None and not self.dry_run

    def start(self) -> RunLog:
        if self.writing:
            with self.conn.cursor() as cur:
                cur.execute("insert into ingestion_runs (job, trigger, gh_run_id) values (%s, %s, %s) returning id",
                            (self.job, self.trigger, self.gh_run_id))
                self.run_id = cur.fetchone()[0]
        log.info("%s run %s started (trigger=%s%s)", self.job, self.run_id or "-", self.trigger,
                 ", dry-run" if self.dry_run else "")
        return self

    @contextmanager
    def step(self, name: str, transactional: bool = True) -> Iterator[dict]:
        """Run one step in its own transaction. A failure is recorded, rolled back and swallowed.

        `transactional=False` is for statements Postgres refuses inside a transaction (VACUUM).
        """
        entry: dict = {"step": name, "ok": True, "ms": 0, "error": None}
        self._step_rows = Counter()
        t0 = time.perf_counter()
        try:
            with self.conn.transaction() if self.writing and transactional else nullcontext():
                yield entry
        except Exception as exc:  # noqa: BLE001: one source failing must not stop the others
            entry.update(ok=False, error=f"{type(exc).__name__}: {exc}"[:500])
            log.exception("step %s failed", name)
        else:
            self.rows_written.update(self._step_rows)
        entry["ms"] = int((time.perf_counter() - t0) * 1000)
        if self._step_rows:
            entry["rows"] = dict(self._step_rows) if entry["ok"] else {}
        self._step_rows = None
        self.steps.append(entry)
        log.info("step %-12s %s %5d ms %s", name, "ok  " if entry["ok"] else "FAIL", entry["ms"],
                 entry.get("note") or entry.get("rows") or "")

    def rows(self, table: str, n: int) -> None:
        if self._step_rows is None:
            raise RuntimeError("rows() must be called inside a step")
        self._step_rows[table] += n

    @property
    def status(self) -> str:
        if not self.steps or not any(s["ok"] for s in self.steps):
            return "failed"
        return "success" if all(s["ok"] for s in self.steps) else "partial"

    def finish(self) -> str:
        status = self.status
        errors = "; ".join(f"{s['step']}: {s['error']}" for s in self.steps if not s["ok"]) or None
        if self.writing:
            with self.conn.cursor() as cur:
                cur.execute(
                    """update ingestion_runs set finished_at = now(), status = %s, rows_written = %s,
                              steps = %s, error = %s where id = %s""",
                    (status, Jsonb(dict(self.rows_written)), Jsonb(self.steps), errors, self.run_id))
        log.info("%s run %s finished: %s %s", self.job, self.run_id or "-", status,
                 json.dumps(dict(self.rows_written)))
        return status


def exit_code(status: str) -> int:
    """0 keeps the workflow green for success and partial runs; 1 turns it red (api-spec §6)."""
    return 1 if status == "failed" else 0
