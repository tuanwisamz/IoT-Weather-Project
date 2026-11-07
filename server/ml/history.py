"""Previous Runs history for the Phase 5b models (Implementation-plan §5.8), cached in 60-day chunks.

    python history.py                 # fetch 30 Sep 2025 → 31 Oct 2026 (GMT dates) into .cache/v2/
    python history.py --until 2026-11-30

The API is slow for many fields at once, so the fields come in two groups. A chunk that ends in the
past never changes, so it is cached; the newest chunk is fetched again when `until` moves.
"""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from iww_ingest import config

HERE = Path(__file__).resolve().parent
CACHE = HERE / ".cache" / "v2"
START = date(2025, 9, 30)                      # GMT date; training starts 1 Oct 2025 00:00 MYT
DEFAULT_UNTIL = date(2026, 10, 31)             # GMT date, inclusive; the report window starts 3 Nov 16:00 UTC
CHUNK_DAYS = 60
DAYS = range(1, 8)
TRUTH = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "pressure_msl", "precipitation"]
LEAD_VARS = ["temperature_2m", "relative_humidity_2m", "dew_point_2m", "precipitation", "wind_speed_10m",
             "wind_direction_10m", "pressure_msl", "cloud_cover", "cape"]
GROUPS = {
    "a": TRUTH + [f"{v}_previous_day{n}" for v in LEAD_VARS[:4] for n in DAYS],
    "b": [f"{v}_previous_day{n}" for v in LEAD_VARS[4:] for n in DAYS],
}


def fetch_chunk(group: str, start: date, end: date, refresh: bool) -> pd.DataFrame:
    path = CACHE / f"{group}_{start}_{end}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path)
    for attempt in range(6):
        try:
            resp = requests.get(config.OM_PREVIOUS_RUNS_URL, timeout=180, params={
                "latitude": config.LAT, "longitude": config.LON, "hourly": ",".join(GROUPS[group]),
                "start_date": start.isoformat(), "end_date": end.isoformat(), "timezone": "GMT"})
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 5:
                raise
            print(f"retrying {group} {start} after {type(exc).__name__}", flush=True)
            time.sleep(20 * (attempt + 1))
    df = pd.DataFrame(resp.json()["hourly"])
    CACHE.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"fetched {group} {start} → {end}", flush=True)
    return df


def fetch(until: date = DEFAULT_UNTIL) -> pd.DataFrame:
    """Wide hourly table: `time` (UTC) plus every field in GROUPS."""
    parts = {}
    for group in GROUPS:
        chunks, start = [], START
        while start <= until:
            end = min(start + timedelta(days=CHUNK_DAYS - 1), until)
            # A chunk ending within the last 8 days may still gain values, so it is never trusted from cache.
            chunks.append(fetch_chunk(group, start, end, refresh=end >= date.today() - timedelta(days=8)))
            start = end + timedelta(days=1)
        parts[group] = pd.concat(chunks, ignore_index=True)
    wide = parts["a"].merge(parts["b"], on="time", how="inner")
    wide["time"] = pd.to_datetime(wide["time"], utc=True)
    return wide


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--until", type=date.fromisoformat, default=DEFAULT_UNTIL)
    df = fetch(p.parse_args().until)
    print(f"{len(df)} hours, {df['time'].min()} → {df['time'].max()}, "
          f"max null share {df.isna().mean().max():.3f}")
