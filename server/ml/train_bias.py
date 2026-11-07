"""Train the temperature bias correction on Open-Meteo Previous Runs history (Implementation-plan §5.4).

    python train_bias.py              # uses .cache/history.csv.gz, fetching it on the first run

Nothing from November 2026 is used, so either candidate report window stays unseen. Only validation
numbers are computed here. The test on the frozen window happens in SQL, after scoring.

Open-Meteo's best_match changed behaviour around Q3 2025: forecasts went from about 1.3 °C too hot to
0.5–1.0 °C too cold, and the day-0 truth moved about 1 °C with them. Training across that break teaches
a correction that no longer holds, so the model trains on TRAIN_START onward. The full history is
trained too, and the comparison on validation data is kept in card.json.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests

from bias_features import FEATURES, add_features
from iww_ingest import config

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache" / "history.csv.gz"
MODEL_DIR = HERE / "models" / "bias_temperature" / "v1.0"

START = "2024-03-01"
END = "2026-10-31"
TRAIN_START = pd.Timestamp("2025-09-30T16:00:00Z")    # 1 Oct 2025 00:00 MYT, after the best_match change
TRAIN_END = pd.Timestamp("2026-06-30T16:00:00Z")      # 1 Jul 00:00 MYT
VALID_END = pd.Timestamp("2026-10-31T16:00:00Z")      # 1 Nov 00:00 MYT
DAYS = range(1, 8)
VARS = {"temperature_2m": "forecast_c", "relative_humidity_2m": "fc_humidity_pct",
        "wind_speed_10m": "fc_wind_speed_kmh", "precipitation": "fc_precipitation_mm"}
PARAMS = {"objective": "regression_l1", "metric": "l1", "learning_rate": 0.05, "num_leaves": 31,
          "min_data_in_leaf": 200, "feature_fraction": 0.8, "bagging_fraction": 0.8, "bagging_freq": 1,
          "seed": 42, "verbosity": -1}


def fetch_chunk(start: pd.Timestamp, end: pd.Timestamp, hourly: list[str]) -> pd.DataFrame:
    path = CACHE.parent / f"chunk_{start.date()}.csv"
    if path.exists():
        return pd.read_csv(path)
    for attempt in range(6):
        try:
            resp = requests.get(config.OM_PREVIOUS_RUNS_URL, timeout=120, params={
                "latitude": config.LAT, "longitude": config.LON, "hourly": ",".join(hourly),
                "start_date": start.date().isoformat(), "end_date": end.date().isoformat(), "timezone": "GMT"})
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 5:
                raise
            print(f"retrying {start.date()} after {type(exc).__name__}")
            time.sleep(15 * (attempt + 1))
    df = pd.DataFrame(resp.json()["hourly"])
    df.to_csv(path, index=False)
    print(f"fetched to {end.date()}")
    return df


def fetch_history() -> pd.DataFrame:
    """Wide hourly history, cached because it's the same every run. The full range is too slow for
    one request, so it comes in 90-day chunks that survive a dropped connection."""
    if CACHE.exists():
        return pd.read_csv(CACHE, parse_dates=["time"])
    CACHE.parent.mkdir(exist_ok=True)
    hourly = ["temperature_2m"] + [f"{v}_previous_day{n}" for v in VARS for n in DAYS]
    chunks = []
    for start in pd.date_range(START, END, freq="90D"):
        chunks.append(fetch_chunk(start, min(start + pd.Timedelta(days=89), pd.Timestamp(END)), hourly))
    df = pd.concat(chunks, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df.to_csv(CACHE, index=False)
    return df


def to_long(wide: pd.DataFrame) -> pd.DataFrame:
    """One row per (target hour, day-lead). Day 0 is the truth; the residual is what the model learns."""
    wide = wide.assign(time=pd.to_datetime(wide["time"], utc=True))
    frames = []
    for n in DAYS:
        frame = pd.DataFrame({"target_time": wide["time"], "lead_hours": 24 * n, "truth_c": wide["temperature_2m"]})
        for var, col in VARS.items():
            frame[col] = wide[f"{var}_previous_day{n}"]
        frames.append(frame)
    long = pd.concat(frames, ignore_index=True).dropna()
    long["residual"] = long["truth_c"] - long["forecast_c"]
    return add_features(long)


def split(long: pd.DataFrame, train_start: pd.Timestamp = TRAIN_START) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = long[(long["target_time"] >= train_start) & (long["target_time"] < TRAIN_END)]
    valid = long[(long["target_time"] >= TRAIN_END) & (long["target_time"] < VALID_END)]
    return train, valid


def mae(values) -> float:
    return float(np.abs(values).mean())


def fit(train: pd.DataFrame, valid: pd.DataFrame) -> tuple[lgb.Booster, dict, pd.Series]:
    booster = lgb.train(
        PARAMS,
        lgb.Dataset(train[FEATURES], train["residual"]),
        num_boost_round=2000,
        valid_sets=[lgb.Dataset(valid[FEATURES], valid["residual"])],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    bias_by_lead = train.groupby("lead_hours")["residual"].median()
    predicted = booster.predict(valid[FEATURES], num_iteration=booster.best_iteration)
    errors = pd.DataFrame({"lead_hours": valid["lead_hours"].values,
                           "raw": -valid["residual"].values,
                           "constant": valid["lead_hours"].map(bias_by_lead).values - valid["residual"].values,
                           "model": predicted - valid["residual"].values})

    def row(g: pd.DataFrame) -> dict:
        return {"n": len(g), "raw_mae": mae(g["raw"]), "constant_bias_mae": mae(g["constant"]),
                "model_mae": mae(g["model"])}

    metrics = {"overall": row(errors),
               "by_lead_hours": {int(lead): row(g) for lead, g in errors.groupby("lead_hours")}}
    return booster, metrics, bias_by_lead


def main() -> None:
    long = to_long(fetch_history())
    train, valid = split(long)
    print(f"train {len(train):,} rows, {train['target_time'].min()} to {train['target_time'].max()}")
    print(f"valid {len(valid):,} rows to {valid['target_time'].max()}")

    booster, metrics, bias_by_lead = fit(train, valid)
    full_train, _ = split(long, long["target_time"].min())
    _, full_metrics, _ = fit(full_train, valid)
    overall = metrics["overall"]

    gain = booster.feature_importance("gain")
    importance = sorted(({"feature": f, "gain": float(g / gain.sum())} for f, g in zip(FEATURES, gain)),
                        key=lambda x: -x["gain"])

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(MODEL_DIR / "model.txt"), num_iteration=booster.best_iteration)
    card = {
        "name": "bias_temperature", "version": "v1.0", "algorithm": "lightgbm", "features": FEATURES,
        "params": PARAMS, "best_iteration": booster.best_iteration,
        "train_window": [str(TRAIN_START), str(TRAIN_END)], "valid_window": [str(TRAIN_END), str(VALID_END)],
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "validation": metrics,
        "full_history_validation": {"train_window": [START, str(TRAIN_END)], "overall": full_metrics["overall"]},
        "constant_bias_by_lead_hours": {int(k): float(v) for k, v in bias_by_lead.items()},
        "importance": importance,
    }
    (MODEL_DIR / "card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")

    print(f"best iteration {booster.best_iteration}")
    print(f"validation MAE: raw {overall['raw_mae']:.4f}, constant bias {overall['constant_bias_mae']:.4f}, "
          f"model {overall['model_mae']:.4f}")
    print(f"full history model: {full_metrics['overall']['model_mae']:.4f}, "
          f"constant bias {full_metrics['overall']['constant_bias_mae']:.4f}")
    for lead, m in metrics["by_lead_hours"].items():
        print(f"  {lead:>3} h  raw {m['raw_mae']:.3f}  constant {m['constant_bias_mae']:.3f}  model {m['model_mae']:.3f}")
    print("importance:", ", ".join(f"{i['feature']} {i['gain']:.2f}" for i in importance[:5]))


if __name__ == "__main__":
    main()
