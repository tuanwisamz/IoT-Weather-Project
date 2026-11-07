"""Constants and environment for every job (architecture §4–6, api-spec §5)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]          # server/ingest
REPO_ROOT = PACKAGE_ROOT.parents[1]
CACHE_DIR = PACKAGE_ROOT / ".cache"
MIGRATIONS_DIR = REPO_ROOT / "database" / "migrations"

# Fixed location: Seri Iskandar (Open-Meteo snaps it to the 4.3937 N, 100.9738 E grid cell).
LOCATION_ID = 1
LAT, LON = 4.35993, 100.98491
LOCAL_TZ = "Asia/Kuala_Lumpur"

OM_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OM_META_URL = "https://api.open-meteo.com/data/{meta_key}/static/meta.json"
OM_PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
METAR_URL = "https://aviationweather.gov/api/data/metar"
METAR_STATION = "WMKI"

# Open-Meteo variable → our column (api-spec §5.1, §5.2).
CURRENT_VARS = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "dew_point_2m": "dew_point_c",
    "precipitation": "precipitation_mm",
    "weather_code": "weather_code",
    "wind_speed_10m": "wind_speed_kmh",
    "wind_direction_10m": "wind_dir_deg",
    "pressure_msl": "pressure_hpa",
    "cloud_cover": "cloud_cover_pct",
}
CURRENT_REQUEST = list(CURRENT_VARS)[:4] + ["rain"] + list(CURRENT_VARS)[4:]

HOURLY_VARS = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "dew_point_2m": "dew_point_c",
    "precipitation": "precipitation_mm",
    "precipitation_probability": "precip_probability_pct",
    "wind_speed_10m": "wind_speed_kmh",
    "wind_direction_10m": "wind_dir_deg",
    "pressure_msl": "pressure_hpa",
    "cloud_cover": "cloud_cover_pct",
    "cape": "cape_jkg",
    "weather_code": "weather_code",
}
DAILY_VARS = {
    "temperature_2m_max": "temp_max_c",
    "temperature_2m_min": "temp_min_c",
    "precipitation_sum": "precipitation_sum_mm",
    "precipitation_probability_max": "precip_probability_max_pct",
    "precipitation_hours": "precipitation_hours",
    "wind_speed_10m_max": "wind_speed_max_kmh",
}
FORECAST_DAYS = 7

# Previous Runs has every hourly variable except rain probability, which is empty for all models.
PREVIOUS_RUNS_VARS = {om: col for om, col in HOURLY_VARS.items() if om != "precipitation_probability"}
PREVIOUS_RUNS_DAYS = range(1, 8)

# Used when the job runs without a database (dry-run): mirrors 0005_seed.sql's active models.
DEFAULT_MODELS = {
    "best_match": None,
    "ecmwf_ifs025": "ecmwf_ifs025",
    "gfs_seamless": "ncep_gfs025",
    "icon_seamless": "dwd_icon",
}

HTTP_TIMEOUT_S = 15
HTTP_BACKOFF_S = (1, 3, 9)
RAW_RETENTION_DAYS = 30


@dataclass(frozen=True)
class Settings:
    db_url: str | None
    contact_email: str | None
    gh_run_id: int | None
    log_level: str


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(REPO_ROOT / ".env", override=False)


def settings() -> Settings:
    _load_dotenv()
    run_id = os.environ.get("GH_RUN_ID")
    return Settings(
        db_url=os.environ.get("SUPABASE_DB_URL") or None,
        contact_email=os.environ.get("CONTACT_EMAIL") or None,
        gh_run_id=int(run_id) if run_id and run_id.isdigit() else None,
        log_level=os.environ.get("IWW_LOG_LEVEL", "INFO").upper(),
    )


def default_trigger() -> str:
    event = os.environ.get("GITHUB_EVENT_NAME")
    return {"schedule": "schedule", "workflow_dispatch": "dispatch"}.get(event or "", "local")
