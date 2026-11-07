"""Monthly retrain: challenger vs champion for every live model (Implementation-plan §5.8, task ML6).

    python retrain.py                         # judge on last month (MYT), activate winners
    python retrain.py --month 2026-10 --dry-run

For each model, a challenger is trained on everything before the month and scored on it, next to the
active champion. Only a challenger that scores better is refit on all the data, including the month,
and activated as the next version; otherwise nothing changes. Either way the comparison is appended to
the champion's `metrics.retrain_checks`. Report versions are never deactivated from the report: the
views keep using them for 4–7 Nov (0008).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone

import lightgbm as lgb
import numpy as np
import pandas as pd
from psycopg.types.json import Jsonb

import history
import train_models as tm
from iww_ingest import config, db
from iww_ingest.ml.models import SPECS, Spec, predictions
from iww_ingest.runlog import RunLog, exit_code


def month_bounds(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Start and end of a local (MYT) month, as UTC instants."""
    start = pd.Timestamp(f"{month}-01T00:00:00+08:00").tz_convert("UTC")
    return start, (start.tz_convert("Asia/Kuala_Lumpur") + pd.offsets.MonthBegin(1)).tz_convert("UTC")


def last_month(today: date) -> str:
    return (pd.Timestamp(today).replace(day=1) - pd.Timedelta(days=1)).strftime("%Y-%m")


def score(spec: Spec, booster, threshold: float | None, df: pd.DataFrame) -> float:
    """Lower is better: MAE for a residual model, Brier for the rain model."""
    raw = booster.predict(tm.features(df))
    if spec.kind == "rain":
        return float(np.mean((raw - tm.label(spec, df)) ** 2))
    corrected = predictions(spec, raw, df[spec.column].to_numpy(dtype=float), threshold)[spec.column]
    return float(np.mean(np.abs(corrected - df[f"truth_{spec.truth}"].to_numpy(dtype=float))))


def next_version(conn, name: str) -> str:
    versions = [r[0] for r in db.fetch_all(conn, "select version from ml_models where name = %s", (name,))]
    minors = [int(v.split(".")[1]) for v in versions if v.startswith("v1.") and v.split(".")[1].isdigit()]
    return f"v1.{max(minors, default=0) + 1}"


def check(conn, spec: Spec, df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    row = db.fetch_all(conn, """select id, version, artifact, metrics, upper(train_window) from ml_models
                                where name = %s and is_active and artifact is not null""", (spec.name,))
    if not row:
        return {"model": spec.name, "decision": "skip: no active model with an artifact"}
    champ_id, champ_version, artifact, metrics, champ_upper = row[0]
    metrics = metrics or {}
    rounds, threshold = metrics.get("rounds", 200), metrics.get("threshold")
    data = tm.usable(spec, df)
    before, month = data[data["target_time"] < start], data[(data["target_time"] >= start) & (data["target_time"] < end)]
    if month.empty:
        return {"model": spec.name, "decision": "skip: no data for the month"}
    challenger = tm.fit(spec, before, rounds)
    result = {"model": spec.name, "champion": champ_version, "n": len(month),
              "metric": "brier" if spec.kind == "rain" else "mae",
              "champion_score": round(score(spec, lgb.Booster(model_str=artifact), threshold, month), 4),
              "challenger_score": round(score(spec, challenger, threshold, month), 4),
              "_champ_id": champ_id, "_rounds": rounds, "_threshold": threshold}
    # A champion that was trained on this month would be judged on data it has seen: never replace on that.
    if champ_upper is not None and champ_upper >= start.to_pydatetime():
        result["decision"] = "keep: the champion was trained on this month, so the comparison isn't fair"
    elif result["challenger_score"] < result["champion_score"]:
        result["decision"] = "replace"
    else:
        result["decision"] = "keep"
    return result


def activate(conn, spec: Spec, df: pd.DataFrame, result: dict, month: str) -> str:
    data = tm.usable(spec, df)
    booster = tm.fit(spec, data, result["_rounds"])
    text = booster.model_to_string()
    version = next_version(conn, spec.name)
    gain = booster.feature_importance("gain")
    conn.execute("update ml_models set is_active = false where name = %s", (spec.name,))
    conn.execute(
        """insert into ml_models (name, version, algorithm, features, train_window, metrics, importance,
                                  artifact_sha256, artifact, is_active, is_report, trained_at)
           values (%s, %s, 'lightgbm', %s, tstzrange(%s::timestamptz, %s::timestamptz, '[]'), %s, %s, %s, %s,
                   true, false, now())""",
        (spec.name, version, tm.bias.FEATURES, data["target_time"].min().to_pydatetime(),
         data["target_time"].max().to_pydatetime(),
         Jsonb({"threshold": result["_threshold"], "rounds": result["_rounds"],
                "replaced": {"version": result["champion"], "month": month,
                             "champion_score": result["champion_score"], "challenger_score": result["challenger_score"]}}),
         Jsonb([{"feature": f, "gain": round(float(g / gain.sum()), 4)} for f, g in zip(tm.bias.FEATURES, gain)]),
         hashlib.sha256(text.encode()).hexdigest(), text))
    return version


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--month", help="YYYY-MM (MYT) to judge on; default: last month")
    p.add_argument("--dry-run", action="store_true", help="compare and print, change nothing")
    p.add_argument("--trigger", choices=["schedule", "dispatch", "local"], default=config.default_trigger())
    args = p.parse_args(argv)
    month = args.month or last_month(date.today())
    start, end = month_bounds(month)
    cfg = config.settings()
    with db.connect(cfg.db_url, "retrain") as conn:
        run = RunLog("retrain", args.trigger, conn, cfg.gh_run_id, args.dry_run).start()
        results = []
        with run.step("history") as step:
            # The month ends at 16:00 UTC on its last GMT date, so that date is the last one needed.
            df = tm.long_frame(history.fetch((end - pd.Timedelta(hours=16)).date()), end)
            step["note"] = f"{len(df)} rows up to {end:%Y-%m-%d %H:%M} UTC, judged on {month}"
        for name, spec in SPECS.items():
            with run.step(name) as step:
                result = check(conn, spec, df, start, end)
                if result["decision"] == "replace" and run.writing:
                    result["activated"] = activate(conn, spec, df, result, month)
                    run.rows("ml_models", 1)
                if run.writing and "_champ_id" in result:
                    public = {k: v for k, v in result.items() if not k.startswith("_")}
                    conn.execute("""update ml_models set metrics = jsonb_set(coalesce(metrics, '{}'), '{retrain_checks}',
                                      coalesce(metrics->'retrain_checks', '[]') || %s) where id = %s""",
                                 (Jsonb([{**public, "month": month, "at": datetime.now(timezone.utc).isoformat()}]),
                                  result["_champ_id"]))
                step["note"] = {k: v for k, v in result.items() if not k.startswith("_")}
                results.append(step["note"])
        status = run.finish()
    print(json.dumps(results, indent=1, default=str))
    return exit_code(status)


if __name__ == "__main__":
    raise SystemExit(main())
