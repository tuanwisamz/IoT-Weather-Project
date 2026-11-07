"""score: hourly, after `forecast`. Correct new Best Match forecasts with each active model (Implementation-plan §5.8).

Models are loaded from `ml_models.artifact`, so a monthly retrain takes effect without a deploy. Each
forecast issue is scored once per model. To bound growth, live predictions are thinned to four issues
a day once they're 3 hours old; retrieved forecasts (the report window) are never touched.
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from typing import Any

import numpy as np

from .. import config, db
from ..features import bias
from ..ml.models import SPECS, Spec, predictions
from ..runlog import RunLog
from ._common import base_parser, run, write

log = logging.getLogger(__name__)
KEY = ("location_id", "model_id", "variable", "issued_at", "target_time")
LOOKBACK_HOURS = 6                 # catches up after a missed run
KEEP_UTC_HOURS = (0, 6, 12, 18)    # issues kept for good after thinning
THIN_AFTER_HOURS = 3


def active_models(conn) -> list[dict[str, Any]]:
    rows = db.fetch_all(conn, """
        select id, name, version, artifact, metrics from ml_models
        where is_active and artifact is not null and name = any(%s) order by name""", (list(SPECS),))
    return [dict(zip(("id", "name", "version", "artifact", "metrics"), r)) for r in rows]


def pending_issues(conn, model_id: int) -> list[datetime]:
    # An issue that `thin` would delete is skipped, or every run would score it again.
    rows = db.fetch_all(conn, f"""
        select distinct f.issued_at from forecasts f
        where f.location_id = %s and f.model = 'best_match' and f.origin = 'snapshot'
          and f.issued_at >= now() - interval '{LOOKBACK_HOURS} hours'
          and (f.issued_at >= now() - interval '{THIN_AFTER_HOURS} hours'
               or extract(hour from f.issued_at at time zone 'UTC') = any(%s))
          and not exists (select 1 from predictions p where p.model_id = %s and p.issued_at = f.issued_at)
        order by 1""", (config.LOCATION_ID, list(KEEP_UTC_HOURS), model_id))
    return [r[0] for r in rows]


def forecast_rows(conn, issued_at: datetime) -> list[dict[str, Any]]:
    cols = ["target_time", "lead_hours", *bias.FORECAST_COLUMNS]
    rows = db.fetch_all(conn, f"""
        select {", ".join(cols)} from forecasts
        where location_id = %s and model = 'best_match' and origin = 'snapshot'
          and issued_at = %s and target_time > issued_at
        order by target_time""", (config.LOCATION_ID, issued_at))
    return [dict(zip(cols, r)) for r in rows]


def score_rows(spec: Spec, booster, threshold: float | None, model_id: int, issued_at: datetime,
               rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prediction rows for one forecast issue. `booster` only needs `.predict(matrix)`."""
    if not rows:
        return []
    values = {c: np.array([np.nan if r[c] is None else r[c] for r in rows], dtype=float)
              for c in bias.FORECAST_COLUMNS + ["lead_hours"]}
    epoch = np.array([r["target_time"].timestamp() for r in rows])
    out = predictions(spec, booster.predict(bias.matrix(values, epoch)), values[spec.column], threshold)
    result = []
    for variable, vals in out.items():
        for r, v, base in zip(rows, vals, values[spec.column]):
            if np.isnan(v):            # a residual model can't correct a missing forecast value
                continue
            result.append({"location_id": config.LOCATION_ID, "model_id": model_id, "issued_at": issued_at,
                           "target_time": r["target_time"], "variable": variable, "value": float(v),
                           "base_model": "best_match", "base_value": None if np.isnan(base) else float(base),
                           "lead_hours": int(r["lead_hours"])})
    return result


def body(runlog: RunLog, args: argparse.Namespace) -> None:
    if runlog.conn is None:
        with runlog.step("score") as step:
            step["note"] = "no database: nothing to score"
        return
    with runlog.step("score") as step:
        import lightgbm as lgb       # only this job needs it (requirements-score.txt)

        notes = []
        for m in active_models(runlog.conn):
            spec = SPECS[m["name"]]
            booster = lgb.Booster(model_str=m["artifact"])
            issues = pending_issues(runlog.conn, m["id"])
            for issued_at in issues:
                rows = score_rows(spec, booster, (m["metrics"] or {}).get("threshold"), m["id"], issued_at,
                                  forecast_rows(runlog.conn, issued_at))
                write(runlog, "predictions", rows, KEY)
            notes.append(f"{m['name']} {m['version']}: {len(issues)} issue(s)")
        step["note"] = "; ".join(notes) or "no active models with an artifact"
    with runlog.step("thin"):
        if runlog.writing:
            with runlog.conn.cursor() as cur:
                cur.execute(f"""
                    delete from predictions p
                    where p.issued_at < now() - interval '{THIN_AFTER_HOURS} hours'
                      and extract(hour from p.issued_at at time zone 'UTC') <> all(%s)
                      and exists (select 1 from forecasts f
                                  where f.location_id = p.location_id and f.model = p.base_model
                                    and f.origin = 'snapshot' and f.issued_at = p.issued_at
                                    and f.target_time = p.target_time)""", (list(KEEP_UTC_HOURS),))
                runlog.rows("predictions_thinned", cur.rowcount)


def parser() -> argparse.ArgumentParser:
    return base_parser("score")


def main(argv: list[str] | None = None) -> int:
    return run("score", parser(), body, argv)


if __name__ == "__main__":
    sys.exit(main())
