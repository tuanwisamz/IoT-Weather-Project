"""Register the Phase 5b models and score the retrieved window once (Implementation-plan §5.8, task ML4).

    python score_models.py --register-only     # load model files into ml_models, set the flags, no scoring
    python score_models.py                     # register, then score 1 Nov 00:00 → 7 Nov 00:00 MYT once

Window rows are scored by the live scorer's own `score_rows`, so the report and live forecasts go
through identical code. v1.0 temperature is left alone: score_window.py made its report figures.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import lightgbm as lgb
from psycopg.types.json import Jsonb

from iww_ingest import config, db
from iww_ingest.features import bias
from iww_ingest.jobs.score import KEY, score_rows
from iww_ingest.ml.models import SPECS
from iww_ingest.runlog import RunLog, exit_code
from score_window import SINCE, UNTIL

HERE = Path(__file__).resolve().parent
REPORT = {"bias_humidity", "bias_wind", "bias_pressure", "rain_occurrence"}   # report and live
LIVE_ONLY = {"bias_temperature"}                                             # v1.1; v1.0 stays the report's


def model_dir(name: str) -> Path:
    return HERE / "models" / name / SPECS[name].version


def register(conn, name: str, *, is_report: bool, activate: bool) -> int:
    path = model_dir(name)
    card = json.loads((path / "card.json").read_text(encoding="utf-8"))
    text = (path / "model.txt").read_text(encoding="utf-8")
    if activate:
        conn.execute("update ml_models set is_active = false where name = %s and version <> %s",
                     (name, card["version"]))
    return conn.execute(
        """insert into ml_models (name, version, algorithm, features, train_window, metrics, importance,
                                  artifact_path, artifact_sha256, artifact, is_active, is_report, trained_at)
           values (%s, %s, 'lightgbm', %s, tstzrange(%s::timestamptz, %s::timestamptz, '[]'), %s, %s, %s, %s, %s,
                   %s, %s, %s)
           on conflict (name, version) do update set features = excluded.features,
             train_window = excluded.train_window, metrics = excluded.metrics, importance = excluded.importance,
             artifact_path = excluded.artifact_path, artifact_sha256 = excluded.artifact_sha256,
             artifact = excluded.artifact, is_active = excluded.is_active, is_report = excluded.is_report,
             trained_at = excluded.trained_at
           returning id""",
        (name, card["version"], card["features"], card["train_window"][0], card["train_window"][1],
         Jsonb({"threshold": card["threshold"], "rounds": card["rounds"], "cv": card["cv"]}),
         Jsonb(card["importance"]), str(path.relative_to(HERE.parents[1]) / "model.txt").replace("\\", "/"),
         hashlib.sha256(text.encode()).hexdigest(), text, activate, is_report, card["trained_at"])).fetchone()[0]


def window_issues(conn) -> dict:
    cols = ["issued_at", "target_time", "lead_hours", *bias.FORECAST_COLUMNS]
    rows = db.fetch_all(conn, f"""
        select {", ".join(cols)} from forecasts
        where location_id = %s and model = 'best_match' and origin = 'previous_runs'
          and target_time >= %s and target_time < %s
        order by issued_at, target_time""", (config.LOCATION_ID, SINCE, UNTIL))
    issues = defaultdict(list)
    for r in rows:
        row = dict(zip(cols, r))
        issues[row.pop("issued_at")].append(row)
    return issues


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--register-only", action="store_true")
    args = p.parse_args()
    cfg = config.settings()
    with db.connect(cfg.db_url, "score") as conn:
        run = RunLog("manual", "local", conn).start()
        ids = {}
        with run.step("register"):
            for name in sorted(REPORT | LIVE_ONLY):
                ids[name] = register(conn, name, is_report=name in REPORT, activate=True)
            run.rows("ml_models", len(ids))
        if not args.register_only:
            with run.step("score_window") as step:
                issues = window_issues(conn)
                for name, model_id in ids.items():
                    card = json.loads((model_dir(name) / "card.json").read_text(encoding="utf-8"))
                    booster = lgb.Booster(model_file=str(model_dir(name) / "model.txt"))
                    rows = [row for issued_at, fc in issues.items()
                            for row in score_rows(SPECS[name], booster, card["threshold"], model_id, issued_at, fc)]
                    run.rows("predictions", db.upsert(conn, "predictions", rows, KEY, "update"))
                step["note"] = f"{sum(len(v) for v in issues.values())} forecast hours in {len(issues)} issues"
        status = run.finish()
    print(f"{status}: {dict(run.rows_written)}")
    return exit_code(status)


if __name__ == "__main__":
    raise SystemExit(main())
