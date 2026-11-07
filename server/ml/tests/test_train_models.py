import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import history  # noqa: E402
import train_models  # noqa: E402
from iww_ingest.features import bias  # noqa: E402
from iww_ingest.ml.models import SPECS, predictions  # noqa: E402


def wide(start: str, hours: int) -> pd.DataFrame:
    """Previous Runs-shaped history: day-0 truth 1 below every day-N forecast."""
    df = pd.DataFrame({"time": pd.date_range(start, periods=hours, freq="h", tz="UTC")})
    for om in history.TRUTH:
        df[om] = 10.0
    for om in history.LEAD_VARS:
        for n in history.DAYS:
            df[f"{om}_previous_day{n}"] = 11.0 + n / 10
    return df


def test_a_retrieved_row_and_a_live_row_with_the_same_values_get_identical_features():
    long = train_models.long_frame(wide("2026-03-01T06:00:00Z", 1))
    row = long[long["lead_hours"] == 48].iloc[0]
    target = datetime(2026, 3, 1, 6, tzinfo=timezone.utc)
    # The same forecast as the forecast job stores it: column names from the `forecasts` table.
    live = {c: np.array([11.2]) for c in bias.FORECAST_COLUMNS} | {"lead_hours": np.array([48])}
    expected = bias.matrix(live, np.array([target.timestamp()]))
    assert np.allclose(train_models.features(long.iloc[[long.index.get_loc(row.name)]]), expected)


def test_local_hour_uses_myt_and_day_of_year_is_not_an_input():
    x = bias.matrix({c: np.zeros(1) for c in bias.FORECAST_COLUMNS + ["lead_hours"]},
                    np.array([datetime(2026, 1, 1, 4, tzinfo=timezone.utc).timestamp()]))   # 12:00 MYT
    row = dict(zip(bias.FEATURES, x[0]))
    assert np.isclose(row["hour_sin"], 0) and np.isclose(row["hour_cos"], -1)
    assert not any(f.startswith("doy") for f in bias.FEATURES)


def test_training_rows_stay_between_1_oct_2025_and_1_nov_2026_myt():
    long = train_models.long_frame(wide("2025-09-29T00:00:00Z", 24 * 400))
    assert long["target_time"].min() >= train_models.TRAIN_START
    assert long["target_time"].max() < train_models.DEFAULT_END
    assert long["target_time"].max() == pd.Timestamp("2026-10-31T15:00:00Z")


def test_each_month_is_held_out_with_a_three_day_gap():
    long = train_models.long_frame(wide("2025-09-30T16:00:00Z", 24 * 120))
    seen = np.zeros(len(long), bool)
    for _, train, test in train_models.folds(long):
        assert not (train & test).any()
        seen |= test
        lo, hi = long.loc[test, "target_time"].min(), long.loc[test, "target_time"].max()
        t = long.loc[train, "target_time"]
        assert ((t < lo - train_models.GAP) | (t > hi + train_models.GAP)).all()
    assert seen.all()


def test_residual_label_is_truth_minus_forecast_and_rain_label_uses_0_1_mm():
    long = train_models.long_frame(wide("2026-03-01T00:00:00Z", 2))
    assert np.allclose(train_models.label(SPECS["bias_humidity"], long), 10.0 - long["humidity_pct"])
    assert (train_models.label(SPECS["rain_occurrence"], long) == 1).all()


def test_corrections_are_clipped_and_rain_gets_a_yes_no():
    hum = predictions(SPECS["bias_humidity"], np.array([5.0, -5.0]), np.array([98.0, 3.0]))
    assert hum["humidity_pct"].tolist() == [100.0, 0.0]
    wind = predictions(SPECS["bias_wind"], np.array([-9.0]), np.array([4.0]))
    assert wind["wind_speed_kmh"].tolist() == [0.0]
    pres = predictions(SPECS["bias_pressure"], np.array([0.4]), np.array([1010.0]))
    assert np.isclose(pres["pressure_hpa"][0], 1010.4)
    rain = predictions(SPECS["rain_occurrence"], np.array([0.2, 0.6]), np.array([0.0, 0.0]), threshold=0.3)
    assert rain["rain_yes"].tolist() == [0.0, 1.0] and rain["rain_prob"].tolist() == [0.2, 0.6]
