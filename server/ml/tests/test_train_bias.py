import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bias_features  # noqa: E402
import score_window  # noqa: E402
import train_bias  # noqa: E402


def wide(start: str, hours: int) -> pd.DataFrame:
    times = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    df = pd.DataFrame({"time": times, "temperature_2m": 28.0})
    for var in train_bias.VARS:
        for n in train_bias.DAYS:
            df[f"{var}_previous_day{n}"] = 30.0 + n
    return df


def test_long_has_one_row_per_hour_and_lead_with_truth_minus_forecast():
    long = train_bias.to_long(wide("2026-01-01", 3))
    assert len(long) == 3 * 7
    row = long[long["lead_hours"] == 72].iloc[0]
    assert row["forecast_c"] == 33.0
    assert row["residual"] == 28.0 - 33.0


def test_rows_with_a_missing_forecast_are_dropped():
    df = wide("2026-01-01", 2)
    df.loc[0, "temperature_2m_previous_day7"] = np.nan
    assert len(train_bias.to_long(df)) == 2 * 7 - 1


def test_split_boundaries_keep_november_out_of_both_sets():
    long = train_bias.to_long(wide("2026-06-30T14:00:00Z", 24 * 130))
    train, valid = train_bias.split(long)
    assert train["target_time"].max() < train_bias.TRAIN_END
    assert valid["target_time"].min() >= train_bias.TRAIN_END
    assert valid["target_time"].max() < pd.Timestamp("2026-10-31T16:00:00Z")   # 1 Nov 00:00 MYT
    assert set(train["target_time"]).isdisjoint(valid["target_time"])


def test_training_starts_after_the_best_match_change():
    long = train_bias.to_long(wide("2025-09-29T00:00:00Z", 24 * 4))
    train, _ = train_bias.split(long)
    assert train["target_time"].min() == train_bias.TRAIN_START
    everything, _ = train_bias.split(long, long["target_time"].min())
    assert len(everything) > len(train)


def test_features_use_local_time_and_no_observed_value():
    assert "truth_c" not in bias_features.FEATURES and "residual" not in bias_features.FEATURES
    long = train_bias.to_long(wide("2026-01-01T04:00:00Z", 1))                  # 12:00 MYT
    assert abs(long.iloc[0]["hour_cos"] + 1) < 1e-9


def test_prediction_rows_add_the_residual_to_the_forecast():
    df = pd.DataFrame({"issued_at": [pd.Timestamp("2026-11-03T16:00:00Z")],
                       "target_time": [pd.Timestamp("2026-11-04T16:00:00Z")],
                       "lead_hours": [24], "forecast_c": [30.0]})
    row = score_window.to_rows(df, [-1.5], model_id=7)[0]
    assert row["value"] == 28.5
    assert row["base_value"] == 30.0
    assert row["variable"] == "temperature_c"
    assert row["base_model"] == "best_match"
    assert row["model_id"] == 7
