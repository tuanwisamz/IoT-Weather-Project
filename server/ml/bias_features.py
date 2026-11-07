"""Temperature bias correction: the features, shared by training and scoring (Implementation-plan §5.4).

Every feature is either known when the forecast was issued or a function of the target time. The
truth is only ever used as the training label, so no observed value can leak into a prediction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = ["forecast_c", "lead_hours", "hour_sin", "hour_cos", "doy_sin", "doy_cos",
            "fc_humidity_pct", "fc_wind_speed_kmh", "fc_precipitation_mm"]
LOCAL_OFFSET_H = 8           # MYT has no daylight saving


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """`df` needs target_time (UTC), forecast_c, lead_hours and the three fc_* columns."""
    local = df["target_time"].dt.tz_convert("UTC") + pd.Timedelta(hours=LOCAL_OFFSET_H)
    hour = local.dt.hour + local.dt.minute / 60
    doy = local.dt.dayofyear
    return df.assign(hour_sin=np.sin(2 * np.pi * hour / 24), hour_cos=np.cos(2 * np.pi * hour / 24),
                     doy_sin=np.sin(2 * np.pi * doy / 365.25), doy_cos=np.cos(2 * np.pi * doy / 365.25))
