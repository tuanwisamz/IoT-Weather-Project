"""METAR WMKI (Ipoh airport, 26 km NE): the real-instrument cross-check (api-spec §5.5)."""
from __future__ import annotations

import math
import re

from .. import config, http
from ..timeutil import from_unix

SOURCE = "metar_wmki"
KT_TO_KMH = 1.852
# Precipitation at the station: RA/DZ, optionally with intensity, vicinity, TS or SH (e.g. -RA, TSRA, +SHRA).
RAIN_RE = re.compile(r"(^|\s)[-+]?(VC)?(TS|SH)?(RA|DZ)")


def fetch(hours: int = 3) -> list[dict]:
    data, _, _ = http.get_json(config.METAR_URL, {"ids": config.METAR_STATION, "format": "json", "hours": hours})
    return data or []


def magnus_rh(temp_c: float | None, dew_c: float | None) -> float | None:
    if temp_c is None or dew_c is None:
        return None
    rh = 100 * math.exp(17.625 * dew_c / (243.04 + dew_c)) / math.exp(17.625 * temp_c / (243.04 + temp_c))
    return round(min(rh, 100.0), 1)


def wx_flags(wx: str | None) -> tuple[bool, bool]:
    """(is_raining, is_thunder). A report without a weather group means no significant weather."""
    if not wx:
        return False, False
    return bool(RAIN_RE.search(wx)), "TS" in wx


def _float(value) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def parse_report(rep: dict) -> dict:
    temp, dew = _float(rep.get("temp")), _float(rep.get("dewp"))
    wspd = _float(rep.get("wspd"))
    raining, thunder = wx_flags(rep.get("wxString"))
    return {
        "location_id": config.LOCATION_ID,
        "source": SOURCE,
        "observed_at": from_unix(rep["obsTime"]),
        "interval_min": None,
        "temperature_c": temp,
        "dew_point_c": dew,
        "humidity_pct": magnus_rh(temp, dew),
        "wind_speed_kmh": round(wspd * KT_TO_KMH, 1) if wspd is not None else None,
        "wind_dir_deg": _float(rep.get("wdir")),          # "VRB" → None
        "pressure_hpa": _float(rep.get("altim")),         # QNH, hPa
        "is_raining": raining,
        "is_thunder": thunder,
        "raw": rep,
    }


def parse(reports: list[dict]) -> list[dict]:
    return [parse_report(r) for r in reports if r.get("obsTime")]
