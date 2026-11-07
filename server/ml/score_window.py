"""Register the trained model and score the retrieved forecasts, once, on the laptop (Implementation-plan §5.4).

    python score_window.py            # 1 Nov 00:00 → 7 Nov 00:00 MYT, leads of 1–7 days

The rows reach the leaderboard through v_forecasts_all as the pseudo-model best_match+ml.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import pandas as pd
from psycopg.types.json import Jsonb

from bias_features import FEATURES, add_features
from iww_ingest import config, db
from iww_ingest.runlog import RunLog, exit_code

HERE = Path(__file__).resolve().parent
MODEL_DIR = HERE / "models" / "bias_temperature" / "v1.0"
SINCE = datetime(2026, 10, 31, 16, tzinfo=timezone.utc)
UNTIL = datetime(2026, 11, 6, 16, tzinfo=timezone.utc)
KEY = ("location_id", "model_id", "variable", "issued_at", "target_time")


def register(conn, card: dict) -> int:
    model_txt = MODEL_DIR / "model.txt"
    sha = hashlib.sha256(model_txt.read_bytes()).hexdigest()
    conn.execute("update ml_models set is_active = false where name = %s and version <> %s",
                 (card["name"], card["version"]))
    return conn.execute(
        """insert into ml_models (name, version, algorithm, features, train_window, metrics, importance,
                                  artifact_path, artifact_sha256, is_active, trained_at)
           values (%s, %s, %s, %s, tstzrange(%s::timestamptz, %s::timestamptz), %s, %s, %s, %s, true, %s)
           on conflict (name, version) do update set features = excluded.features,
             train_window = excluded.train_window, metrics = excluded.metrics, importance = excluded.importance,
             artifact_sha256 = excluded.artifact_sha256, is_active = true, trained_at = excluded.trained_at
           returning id""",
        (card["name"], card["version"], card["algorithm"], card["features"],
         card["train_window"][0], card["train_window"][1], Jsonb(card["validation"]), Jsonb(card["importance"]),
         "server/ml/models/bias_temperature/v1.0/model.txt", sha, card["trained_at"])).fetchone()[0]


def load_forecasts(conn) -> pd.DataFrame:
    rows = db.fetch_all(conn, """
        select issued_at, target_time, lead_hours, temperature_c, humidity_pct, wind_speed_kmh, precipitation_mm
        from forecasts
        where model = 'best_match' and origin = 'previous_runs' and location_id = %s
          and target_time >= %s and target_time < %s
          and temperature_c is not null and humidity_pct is not null
          and wind_speed_kmh is not null and precipitation_mm is not null""",
        (config.LOCATION_ID, SINCE, UNTIL))
    df = pd.DataFrame(rows, columns=["issued_at", "target_time", "lead_hours", "forecast_c", "fc_humidity_pct",
                                     "fc_wind_speed_kmh", "fc_precipitation_mm"])
    df["target_time"] = pd.to_datetime(df["target_time"], utc=True)
    return add_features(df)


def to_rows(df: pd.DataFrame, residuals, model_id: int) -> list[dict]:
    return [{"location_id": config.LOCATION_ID, "model_id": model_id, "issued_at": r.issued_at,
             "target_time": r.target_time.to_pydatetime(), "variable": "temperature_c",
             "value": float(r.forecast_c + residual), "base_model": "best_match",
             "base_value": float(r.forecast_c), "lead_hours": int(r.lead_hours)}
            for r, residual in zip(df.itertuples(), residuals)]


def main() -> int:
    cfg = config.settings()
    card = json.loads((MODEL_DIR / "card.json").read_text(encoding="utf-8"))
    booster = lgb.Booster(model_file=str(MODEL_DIR / "model.txt"))
    with db.connect(cfg.db_url, "score") as conn:
        run = RunLog("manual", "local", conn).start()
        with run.step("score_window"):
            model_id = register(conn, card)
            df = load_forecasts(conn)
            rows = to_rows(df, booster.predict(df[FEATURES]), model_id)
            run.rows("predictions", db.upsert(conn, "predictions", rows, KEY, "update"))
        status = run.finish()
    print(f"{status}: {len(rows)} predictions")
    return exit_code(status)


if __name__ == "__main__":
    raise SystemExit(main())
