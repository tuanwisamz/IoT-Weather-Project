"""Inputs for the Phase 5b correction models, shared by training, window scoring and live scoring
(Implementation-plan §5.8). One function builds them, so the three can't drift apart.

Every input is known when the forecast is issued: the forecast's own values, its lead and the local
hour of the target. Day of year is left out on purpose: with about a year of usable history it made
humidity and rain worse on seasons the model hadn't seen (ML-research §3.2).
"""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np

# Raw forecast columns, named as in the `forecasts` table.
FORECAST_COLUMNS = ["temperature_c", "humidity_pct", "dew_point_c", "precipitation_mm", "wind_speed_kmh",
                    "wind_dir_deg", "pressure_hpa", "cloud_cover_pct", "cape_jkg"]
FEATURES = ["temperature_c", "humidity_pct", "dew_point_c", "precipitation_mm", "wind_speed_kmh",
            "wind_dir_sin", "wind_dir_cos", "pressure_hpa", "cloud_cover_pct", "cape_jkg",
            "lead_hours", "hour_sin", "hour_cos"]
LOCAL_OFFSET_S = 8 * 3600        # MYT has no daylight saving


def matrix(values: Mapping[str, np.ndarray], target_epoch_s: np.ndarray) -> np.ndarray:
    """Feature matrix in FEATURES order.

    `values` maps each FORECAST_COLUMNS name and `lead_hours` to a 1-D array; missing values are NaN,
    which LightGBM handles. `target_epoch_s` is the target hour as Unix seconds (UTC).
    """
    col = {k: np.asarray(values[k], dtype=float) for k in FORECAST_COLUMNS + ["lead_hours"]}
    hour = ((np.asarray(target_epoch_s, dtype=float) + LOCAL_OFFSET_S) % 86400) / 3600
    wdir = np.radians(col["wind_dir_deg"])
    derived = {"wind_dir_sin": np.sin(wdir), "wind_dir_cos": np.cos(wdir),
               "hour_sin": np.sin(2 * np.pi * hour / 24), "hour_cos": np.cos(2 * np.pi * hour / 24)}
    return np.column_stack([derived[f] if f in derived else col[f] for f in FEATURES])
