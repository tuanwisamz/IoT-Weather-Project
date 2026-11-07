"""Train the Phase 5b correction models on Previous Runs history (Implementation-plan §5.8, ML-research §4).

    python train_models.py                        # all five, data up to 1 Nov 2026 00:00 MYT
    python train_models.py --only bias_wind

Each model is cross-validated month by month (13 folds, a 3-day gap each side); the number of rounds
and the rain cut-off are picked there, never on the report window. The model is then refit on all the
data and written to models/<name>/<version>/ with a card.json holding the CV results and baselines.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

import history
from iww_ingest import config
from iww_ingest.features import bias
from iww_ingest.ml.models import RAIN_MM, SPECS, Spec, predictions

HERE = Path(__file__).resolve().parent
MODELS_DIR = HERE / "models"
TRAIN_START = pd.Timestamp("2025-09-30T16:00:00Z")     # 1 Oct 2025 00:00 MYT, after the best_match change
DEFAULT_END = pd.Timestamp("2026-10-31T16:00:00Z")     # 1 Nov 2026 00:00 MYT, before either report window
GAP = pd.Timedelta(days=3)
ROUNDS = (100, 200, 400)
THRESHOLDS = np.round(np.arange(0.10, 0.86, 0.05), 2)
PARAMS = {"learning_rate": 0.05, "num_leaves": 31, "min_data_in_leaf": 200, "feature_fraction": 0.8,
          "bagging_fraction": 0.8, "bagging_freq": 1, "seed": 42, "verbosity": -1}
OM_TO_COLUMN = {om: col for om, col in config.HOURLY_VARS.items() if col in bias.FORECAST_COLUMNS}


def long_frame(wide: pd.DataFrame, end: pd.Timestamp = DEFAULT_END) -> pd.DataFrame:
    """One row per (target hour, lead day), with forecast columns named as in `forecasts`."""
    frames = []
    for n in history.DAYS:
        f = pd.DataFrame({"target_time": wide["time"], "lead_hours": 24 * n})
        for om, col in OM_TO_COLUMN.items():
            f[col] = wide[f"{om}_previous_day{n}"]
        for om in history.TRUTH:
            f[f"truth_{om}"] = wide[om]
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    df = df[(df["target_time"] >= TRAIN_START) & (df["target_time"] < end)].reset_index(drop=True)
    df["epoch_s"] = df["target_time"].astype("int64") // 10**9
    df["local_hour"] = (df["epoch_s"] + bias.LOCAL_OFFSET_S) % 86400 // 3600
    return df


def features(df: pd.DataFrame) -> np.ndarray:
    return bias.matrix({c: df[c].to_numpy() for c in bias.FORECAST_COLUMNS + ["lead_hours"]},
                       df["epoch_s"].to_numpy())


def usable(spec: Spec, df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=[spec.column, f"truth_{spec.truth}"]).reset_index(drop=True)


def label(spec: Spec, df: pd.DataFrame) -> np.ndarray:
    truth = df[f"truth_{spec.truth}"].to_numpy(dtype=float)
    if spec.kind == "rain":
        return (truth >= RAIN_MM).astype(float)
    return truth - df[spec.column].to_numpy(dtype=float)


def params(spec: Spec) -> dict:
    if spec.kind == "rain":
        return {**PARAMS, "objective": "binary", "metric": "binary_logloss"}
    return {**PARAMS, "objective": "regression_l1", "metric": "l1"}


def folds(df: pd.DataFrame):
    month = (df["target_time"] + pd.Timedelta(hours=8)).dt.strftime("%Y-%m")
    for m in sorted(month.unique()):
        test = (month == m).to_numpy()
        lo, hi = df.loc[test, "target_time"].min(), df.loc[test, "target_time"].max()
        train = ~test & ((df["target_time"] < lo - GAP) | (df["target_time"] > hi + GAP)).to_numpy()
        yield m, train, test


def csi(yes: np.ndarray, obs: np.ndarray) -> float:
    return float((yes & obs).sum() / max((yes | obs).sum(), 1))


def cross_validate(spec: Spec, df: pd.DataFrame) -> dict:
    """Out-of-fold predictions for every month, at each candidate round count, plus the baselines."""
    X, y = features(df), label(spec, df)
    oof = {r: np.full(len(df), np.nan) for r in ROUNDS}
    baseline = np.full(len(df), np.nan)
    months = np.empty(len(df), dtype=object)
    for m, tr, te in folds(df):
        booster = lgb.train(params(spec), lgb.Dataset(X[tr], y[tr]), max(ROUNDS))
        for r in ROUNDS:
            oof[r][te] = booster.predict(X[te], num_iteration=r)
        train = df[tr].assign(y=y[tr])
        if spec.kind == "rain":         # climatology: the rain frequency by local hour
            table = train.groupby("local_hour")["y"].mean()
            baseline[te] = df.loc[te, "local_hour"].map(table).to_numpy()
        else:                           # the MOS-style baseline: median error per lead day and local hour
            table = train.groupby(["lead_hours", "local_hour"])["y"].median()
            baseline[te] = pd.MultiIndex.from_frame(df.loc[te, ["lead_hours", "local_hour"]]).map(table).to_numpy()
        months[te] = m
    return {"oof": oof, "baseline": baseline, "months": months, "y": y}


def regression_report(spec: Spec, df: pd.DataFrame, cv: dict) -> tuple[int, dict]:
    truth = df[f"truth_{spec.truth}"].to_numpy(dtype=float)
    raw = df[spec.column].to_numpy(dtype=float)

    def corrected(residual):
        return predictions(spec, residual, raw)[spec.column]

    loss = {r: float(np.mean(np.abs(corrected(p) - truth))) for r, p in cv["oof"].items()}
    best = min(loss, key=loss.get)
    series = {"raw": raw, "time_of_day": corrected(cv["baseline"]), "model": corrected(cv["oof"][best])}

    def stats(mask):
        return {k: {"mae": round(float(np.mean(np.abs(v[mask] - truth[mask]))), 4),
                    "bias": round(float(np.mean(v[mask] - truth[mask])), 4)} for k, v in series.items()}

    every = np.ones(len(df), bool)
    leads = df["lead_hours"].to_numpy()
    report = {"n": len(df), "rounds_mae": {str(r): round(v, 4) for r, v in loss.items()}, "overall": stats(every),
              "by_lead_hours": {str(h): stats(leads == h) for h in sorted(set(leads))},
              "by_month": {m: stats(cv["months"] == m) for m in sorted(set(cv["months"]))},
              "spread": {"truth_sd": round(float(np.std(truth)), 4), "model_sd": round(float(np.std(series["model"])), 4)}}
    return best, report


def rain_report(df: pd.DataFrame, cv: dict) -> tuple[int, float, dict]:
    obs = cv["y"].astype(bool)
    loss = {r: float(np.mean((p - obs) ** 2)) for r, p in cv["oof"].items()}
    best = min(loss, key=loss.get)
    p = cv["oof"][best]
    threshold = float(max(THRESHOLDS, key=lambda t: csi(p >= t, obs)))
    raw_yes = df["precipitation_mm"].to_numpy(dtype=float) >= RAIN_MM
    clim = float(np.mean((cv["baseline"] - obs) ** 2))
    leads = df["lead_hours"].to_numpy()

    def at(mask):
        return {"csi_raw": round(csi(raw_yes[mask], obs[mask]), 4),
                "csi_model": round(csi((p >= threshold)[mask], obs[mask]), 4),
                "brier_climatology": round(float(np.mean((cv["baseline"][mask] - obs[mask]) ** 2)), 4),
                "brier_model": round(float(np.mean((p[mask] - obs[mask]) ** 2)), 4)}

    bins = pd.cut(p, [0, 0.2, 0.4, 0.6, 0.8, 1.0], include_lowest=True)
    reliability = (pd.DataFrame({"p": p, "o": obs, "b": bins}).groupby("b", observed=True)
                   .agg(mean_p=("p", "mean"), obs_freq=("o", "mean"), n=("o", "size")).round(4).reset_index())
    report = {"n": len(df), "rain_rate": round(float(obs.mean()), 4), "rounds_brier": {str(r): round(v, 4) for r, v in loss.items()},
              "threshold": threshold, "overall": at(np.ones(len(df), bool)),
              "brier_skill_vs_climatology": round(1 - loss[best] / clim, 4),
              "freq_bias": {"raw": round(float(raw_yes.sum() / max(obs.sum(), 1)), 3),
                            "model": round(float((p >= threshold).sum() / max(obs.sum(), 1)), 3)},
              "by_lead_hours": {str(h): at(leads == h) for h in sorted(set(leads))},
              "by_month": {m: at(cv["months"] == m) for m in sorted(set(cv["months"]))},
              "reliability": reliability.astype({"b": str}).to_dict("records")}
    return best, threshold, report


def fit(spec: Spec, df: pd.DataFrame, rounds: int) -> lgb.Booster:
    return lgb.train(params(spec), lgb.Dataset(features(df), label(spec, df)), rounds)


def train_one(spec: Spec, df: pd.DataFrame, version: str | None = None) -> tuple[lgb.Booster, dict]:
    df = usable(spec, df)
    cv = cross_validate(spec, df)
    threshold = None
    if spec.kind == "rain":
        rounds, threshold, report = rain_report(df, cv)
    else:
        rounds, report = regression_report(spec, df, cv)
    booster = fit(spec, df, rounds)
    gain = booster.feature_importance("gain")
    card = {
        "name": spec.name, "version": version or spec.version, "algorithm": "lightgbm",
        "kind": spec.kind, "column": spec.column, "truth": spec.truth, "clip": [spec.lo, spec.hi],
        "features": bias.FEATURES, "params": params(spec), "rounds": rounds, "threshold": threshold,
        "train_window": [str(df["target_time"].min()), str(df["target_time"].max())],
        "trained_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "cv": report,
        "importance": sorted(({"feature": f, "gain": round(float(g / gain.sum()), 4)} for f, g in zip(bias.FEATURES, gain)),
                             key=lambda r: -r["gain"]),
    }
    return booster, card


def save(booster: lgb.Booster, card: dict) -> Path:
    out = MODELS_DIR / card["name"] / card["version"]
    out.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out / "model.txt"))
    (out / "card.json").write_text(json.dumps(card, indent=2), encoding="utf-8")
    return out


def summary(card: dict) -> str:
    cv = card["cv"]
    if card["kind"] == "rain":
        o = cv["overall"]
        return (f"CSI raw {o['csi_raw']:.3f} → model {o['csi_model']:.3f} (cut-off {card['threshold']}), "
                f"Brier climatology {o['brier_climatology']:.4f} → model {o['brier_model']:.4f}, rounds {card['rounds']}")
    o = cv["overall"]
    return (f"MAE raw {o['raw']['mae']:.3f} → time-of-day {o['time_of_day']['mae']:.3f} → model "
            f"{o['model']['mae']:.3f}, rounds {card['rounds']}")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--only", help="comma-separated model names")
    p.add_argument("--until", type=date.fromisoformat, default=date(2026, 10, 31),
                   help="last GMT date of history to use (the default keeps all of November out)")
    args = p.parse_args()
    end = min(DEFAULT_END, pd.Timestamp(args.until, tz="UTC") + pd.Timedelta(hours=16))
    df = long_frame(history.fetch(args.until), end)
    print(f"{len(df)} rows, {df['target_time'].min()} → {df['target_time'].max()}")
    for name in (args.only.split(",") if args.only else SPECS):
        booster, card = train_one(SPECS[name], df)
        print(f"{name} {card['version']}: {summary(card)} → {save(booster, card)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
