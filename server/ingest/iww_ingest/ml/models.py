"""The Phase 5b correction models and how their raw output becomes stored predictions
(Implementation-plan §5.8). Training, window scoring and live scoring all go through `predictions()`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

RAIN_MM = 0.1        # a rain hour, the same threshold the views use


@dataclass(frozen=True)
class Spec:
    name: str
    version: str
    column: str                      # the forecast column it corrects (or reads, for rain)
    truth: str                       # the Previous Runs day-0 field it learns from
    kind: str                        # "residual" (regression on truth − forecast) or "rain"
    lo: float | None = None
    hi: float | None = None


SPECS = {s.name: s for s in [
    Spec("bias_temperature", "v1.1", "temperature_c", "temperature_2m", "residual"),
    Spec("bias_humidity", "v1.0", "humidity_pct", "relative_humidity_2m", "residual", 0, 100),
    Spec("bias_wind", "v1.0", "wind_speed_kmh", "wind_speed_10m", "residual", 0, None),
    Spec("bias_pressure", "v1.0", "pressure_hpa", "pressure_msl", "residual"),
    Spec("rain_occurrence", "v1.0", "precipitation_mm", "precipitation", "rain"),
]}


def predictions(spec: Spec, raw_output: np.ndarray, base: np.ndarray,
                threshold: float | None = None) -> dict[str, np.ndarray]:
    """Stored variable → values, from the booster's raw output and the raw forecast `base`.

    A residual model adds its output to the forecast and clips. The rain model's output is already a
    probability; it also gets a yes/no at the cut-off chosen in cross-validation.
    """
    out = np.asarray(raw_output, dtype=float)
    if spec.kind == "rain":
        if threshold is None:
            raise ValueError("the rain model needs its threshold")
        return {"rain_prob": out, "rain_yes": (out >= threshold).astype(float)}
    corrected = np.asarray(base, dtype=float) + out
    if spec.lo is not None or spec.hi is not None:
        corrected = np.clip(corrected, spec.lo, spec.hi)
    return {spec.column: corrected}
